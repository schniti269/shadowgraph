import * as fs from 'fs';
import * as path from 'path';
import * as vscode from 'vscode';
import type { ThoughtRow, AnchorRow } from './types';

// sql.js types
interface SqlJsStatic {
    Database: new (data?: ArrayLike<number>) => SqlJsDatabase;
}

interface SqlJsDatabase {
    run(sql: string, params?: unknown[]): void;
    prepare(sql: string): SqlJsStatement;
    export(): Uint8Array;
    close(): void;
}

interface SqlJsStatement {
    bind(params?: Record<string, unknown>): void;
    step(): boolean;
    getAsObject(): Record<string, unknown>;
    free(): void;
}

export class ShadowDatabase {
    private db: SqlJsDatabase | null = null;
    private SQL: SqlJsStatic | null = null;

    constructor(
        private context: vscode.ExtensionContext,
        private dbPath: string
    ) {}

    async initialize(): Promise<void> {
        const wasmPath = path.join(
            this.context.extensionPath,
            'dist',
            'sql-wasm.wasm'
        );

        // Dynamic import of sql.js
        const initSqlJs = require('sql.js') as (options: {
            locateFile: () => string;
        }) => Promise<SqlJsStatic>;

        this.SQL = await initSqlJs({
            locateFile: () => wasmPath,
        });

        this.loadFromDisk();
    }

    private loadFromDisk(): void {
        if (!this.SQL) {
            return;
        }

        if (fs.existsSync(this.dbPath)) {
            const buffer = fs.readFileSync(this.dbPath);
            this.db = new this.SQL.Database(new Uint8Array(buffer));
        } else {
            this.db = new this.SQL.Database();
            this.applySchema();
            this.saveToDisk();
        }
    }

    private applySchema(): void {
        const schemaPath = path.join(
            this.context.extensionPath,
            'src',
            'server',
            'schema.sql'
        );
        const schema = fs.readFileSync(schemaPath, 'utf-8');
        this.db!.run(schema);
    }

    private saveToDisk(): void {
        const dir = path.dirname(this.dbPath);
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true });
        }
        const data = this.db!.export();
        fs.writeFileSync(this.dbPath, Buffer.from(data));
    }

    reload(): void {
        if (this.db) {
            this.db.close();
            this.db = null;
        }
        this.loadFromDisk();
    }

    getThoughtsForSymbol(
        filePath: string,
        symbolName: string
    ): ThoughtRow[] {
        if (!this.db) {
            return [];
        }

        try {
            const stmt = this.db.prepare(`
                SELECT n.id, n.content, COALESCE(n.created_at, '') as created_at FROM nodes n
                JOIN edges e ON e.target_id = n.id
                JOIN anchors a ON a.node_id = e.source_id
                WHERE a.file_path = :filePath
                  AND a.symbol_name = :symbolName
                  AND n.type = 'THOUGHT'
                ORDER BY n.created_at DESC
            `);
            stmt.bind({ ':filePath': filePath, ':symbolName': symbolName });

            const results: ThoughtRow[] = [];
            while (stmt.step()) {
                const row = stmt.getAsObject();
                results.push({
                    id: row['id'] as string,
                    content: row['content'] as string,
                    created_at: (row['created_at'] as string) || undefined,
                });
            }
            stmt.free();
            return results;
        } catch (err) {
            // Database schema doesn't have created_at yet - fallback to basic query
            console.log('[ShadowGraph] Schema migration needed, using fallback query');
            try {
                const stmt = this.db.prepare(`
                    SELECT n.id, n.content FROM nodes n
                    JOIN edges e ON e.target_id = n.id
                    JOIN anchors a ON a.node_id = e.source_id
                    WHERE a.file_path = :filePath
                      AND a.symbol_name = :symbolName
                      AND n.type = 'THOUGHT'
                `);
                stmt.bind({ ':filePath': filePath, ':symbolName': symbolName });

                const results: ThoughtRow[] = [];
                while (stmt.step()) {
                    const row = stmt.getAsObject();
                    results.push({
                        id: row['id'] as string,
                        content: row['content'] as string,
                        created_at: undefined,
                    });
                }
                stmt.free();
                return results;
            } catch (fallbackErr) {
                console.error('[ShadowGraph] Failed to query thoughts:', fallbackErr);
                return [];
            }
        }
    }

    getAnchorsForFile(filePath: string): AnchorRow[] {
        if (!this.db) {
            return [];
        }

        const stmt = this.db.prepare(
            'SELECT * FROM anchors WHERE file_path = :filePath'
        );
        stmt.bind({ ':filePath': filePath });

        const results: AnchorRow[] = [];
        while (stmt.step()) {
            const row = stmt.getAsObject();
            results.push({
                node_id: row['node_id'] as string,
                file_path: row['file_path'] as string,
                symbol_name: row['symbol_name'] as string,
                ast_hash: row['ast_hash'] as string,
                start_line: row['start_line'] as number,
                status: row['status'] as 'VALID' | 'STALE',
            });
        }
        stmt.free();
        return results;
    }

    getStaleAnchors(filePath: string): AnchorRow[] {
        if (!this.db) {
            return [];
        }

        const stmt = this.db.prepare(
            "SELECT * FROM anchors WHERE file_path = :filePath AND status = 'STALE'"
        );
        stmt.bind({ ':filePath': filePath });

        const results: AnchorRow[] = [];
        while (stmt.step()) {
            const row = stmt.getAsObject();
            results.push({
                node_id: row['node_id'] as string,
                file_path: row['file_path'] as string,
                symbol_name: row['symbol_name'] as string,
                ast_hash: row['ast_hash'] as string,
                start_line: row['start_line'] as number,
                status: row['status'] as 'VALID' | 'STALE',
            });
        }
        stmt.free();
        return results;
    }

    /**
     * Write a thought directly from the extension (bypasses MCP channel).
     * Used by the addThought command.
     */
    addThought(
        filePath: string,
        symbolName: string,
        thoughtText: string
    ): string {
        if (!this.db) {
            throw new Error('Database not initialized');
        }

        const codeNodeId = `code:${filePath}:${symbolName}`;
        const thoughtId = `thought:${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;

        this.db.run(
            "INSERT OR REPLACE INTO nodes (id, type, content) VALUES (?, ?, ?)",
            [thoughtId, 'THOUGHT', thoughtText]
        );
        this.db.run(
            "INSERT OR IGNORE INTO edges (source_id, target_id, relation) VALUES (?, ?, ?)",
            [codeNodeId, thoughtId, 'HAS_THOUGHT']
        );

        this.saveToDisk();
        return thoughtId;
    }

    getSymbolNames(filePath: string): string[] {
        if (!this.db) {
            return [];
        }

        const stmt = this.db.prepare(
            'SELECT DISTINCT symbol_name FROM anchors WHERE file_path = :filePath'
        );
        stmt.bind({ ':filePath': filePath });

        const results: string[] = [];
        while (stmt.step()) {
            const row = stmt.getAsObject();
            results.push(row['symbol_name'] as string);
        }
        stmt.free();
        return results;
    }
}
