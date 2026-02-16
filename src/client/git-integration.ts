/**
 * Git integration for ShadowGraph.
 *
 * Watches .shadow/graph.jsonl for changes (from git pulls or manual updates).
 * When the JSONL file changes, automatically merges it back into the local database.
 * Enables team collaboration via git-tracked semantic graphs.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { spawn, spawnSync } from 'child_process';
import { ShadowDatabase } from './database';

/**
 * Manages git integration: watches .shadow/graph.jsonl and syncs with local database.
 */
export class GitIntegrationManager {
    private watcher: vscode.FileSystemWatcher | null = null;
    private lastModified: number = 0;
    private debounceTimer: NodeJS.Timeout | null = null;

    constructor(
        private readonly workspaceFolder: vscode.WorkspaceFolder,
        private readonly db: ShadowDatabase,
        private readonly pythonPath: string,
        private readonly dbPath: string
    ) {}

    /**
     * Start watching .shadow/graph.jsonl for changes.
     */
    activate(): void {
        const graphPath = path.join(this.workspaceFolder.uri.fsPath, '.shadow', 'graph.jsonl');

        console.log('[ShadowGraph Git] Starting git integration watcher for:', graphPath);

        // Watch .shadow/graph.jsonl
        this.watcher = vscode.workspace.createFileSystemWatcher(
            new vscode.RelativePattern(this.workspaceFolder, '.shadow/graph.jsonl')
        );

        // Debounce handler: multiple rapid file changes (from git) should be treated as one
        const handleChange = () => {
            if (this.debounceTimer) {
                clearTimeout(this.debounceTimer);
            }

            this.debounceTimer = setTimeout(() => {
                this.onGraphJsonlChanged(graphPath);
            }, 500);
        };

        this.watcher.onDidChange(handleChange);
        this.watcher.onDidCreate(handleChange);

        console.log('[ShadowGraph Git] Watching .shadow/graph.jsonl for team collaboration');
    }

    /**
     * Handle changes to graph.jsonl file.
     * Merge JSONL into local database.
     */
    private async onGraphJsonlChanged(graphPath: string): Promise<void> {
        try {
            // Check file modification time to avoid re-processing
            const stats = fs.statSync(graphPath);
            if (stats.mtimeMs <= this.lastModified) {
                return;  // Already processed this version
            }
            this.lastModified = stats.mtimeMs;

            console.log('[ShadowGraph Git] graph.jsonl changed, syncing to local database...');

            // Call Python deserializer to merge JSONL into database
            const result = await this.deserializeAndMerge(graphPath);

            if (result.status === 'ok') {
                console.log('[ShadowGraph Git] Graph synced successfully:', result.message);
                // Refresh UI to show merged changes
                this.db.reload();
                vscode.window.showInformationMessage(
                    `[ShadowGraph] Graph synced from .shadow/graph.jsonl (${result.nodes || 0} nodes merged)`
                );
            } else {
                console.error('[ShadowGraph Git] Merge failed:', result.error);
                vscode.window.showWarningMessage(
                    '[ShadowGraph] Failed to merge graph.jsonl. Check console for details.'
                );
            }
        } catch (err) {
            console.error('[ShadowGraph Git] Error handling graph.jsonl change:', err);
            vscode.window.showErrorMessage(
                `[ShadowGraph] Error syncing graph.jsonl: ${err}`
            );
        }
    }

    /**
     * Call Python deserializer to merge JSONL into database.
     */
    private deserializeAndMerge(graphPath: string): Promise<any> {
        return new Promise((resolve, reject) => {
            const serverPath = path.join(
                this.workspaceFolder.uri.fsPath,
                'src',
                'server'
            );

            // Python script to deserialize and merge
            const scriptContent = `
import json
import sys
sys.path.insert(0, '${serverPath}')

from deserializer import deserialize_database

try:
    deserialize_database('${graphPath}', '${this.dbPath}', merge_mode=True)
    print(json.dumps({
        "status": "ok",
        "message": "Graph merged successfully",
        "nodes": 1
    }))
except Exception as e:
    print(json.dumps({
        "status": "error",
        "error": str(e)
    }))
`;

            const python = spawn(this.pythonPath, ['-c', scriptContent]);

            let output = '';
            python.stdout.on('data', (data: Buffer) => {
                output += data.toString();
            });

            python.stderr.on('data', (data: Buffer) => {
                console.error('[ShadowGraph Git] Python stderr:', data.toString());
            });

            python.on('close', (code: number) => {
                try {
                    const result = JSON.parse(output);
                    resolve(result);
                } catch {
                    reject(new Error(`Failed to parse Python output: ${output}`));
                }
            });
        });
    }

    /**
     * Export current database to graph.jsonl for sharing.
     */
    async exportAndCommit(): Promise<void> {
        try {
            const graphPath = path.join(this.workspaceFolder.uri.fsPath, '.shadow', 'graph.jsonl');

            console.log('[ShadowGraph Git] Exporting database to', graphPath);

            // Create .shadow directory if needed
            const shadowDir = path.dirname(graphPath);
            if (!fs.existsSync(shadowDir)) {
                fs.mkdirSync(shadowDir, { recursive: true });
            }

            const serverPath = path.join(
                this.workspaceFolder.uri.fsPath,
                'src',
                'server'
            );

            // Call Python serializer
            const scriptContent = `
import json
import sys
sys.path.insert(0, '${serverPath}')

from serializer import serialize_database

try:
    serialize_database('${this.dbPath}', '${graphPath}')
    print(json.dumps({
        "status": "ok",
        "message": "Graph exported successfully"
    }))
except Exception as e:
    print(json.dumps({
        "status": "error",
        "error": str(e)
    }))
`;

            const result = spawnSync(this.pythonPath, ['-c', scriptContent], {
                encoding: 'utf-8',
            });

            if (result.error) {
                throw result.error;
            }

            const output = JSON.parse(result.stdout);
            if (output.status !== 'ok') {
                throw new Error(output.error);
            }

            console.log('[ShadowGraph Git] Graph exported. Commit .shadow/graph.jsonl to share with team.');
            vscode.window.showInformationMessage(
                '[ShadowGraph] Graph exported to .shadow/graph.jsonl. Commit this file to share with your team.'
            );
        } catch (err) {
            console.error('[ShadowGraph Git] Export failed:', err);
            vscode.window.showErrorMessage(
                `[ShadowGraph] Failed to export graph: ${err}`
            );
        }
    }

    /**
     * Dispose watchers and cleanup.
     */
    dispose(): void {
        if (this.watcher) {
            this.watcher.dispose();
        }
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
    }
}

/**
 * Show git integration status and instructions.
 */
export function showGitIntegrationStatus(): void {
    const message = `
[ShadowGraph Git Integration]

Graph Sharing via Git:
- Your semantic graph is stored in: .shadow/graph.jsonl
- This file is designed to be git-tracked (not .gitignored)
- Commit and push this file to share your graph with teammates

Team Collaboration:
1. Make changes locally (add thoughts, index files)
2. Run: ShadowGraph: Export Graph
3. Commit and push .shadow/graph.jsonl
4. Teammates pull and automatically sync their databases

Merge Conflicts:
- If .shadow/graph.jsonl has conflicts:
  Run: ShadowGraph: Resolve Graph Conflicts
  (Uses timestamp-based merging to preserve both versions)

Enable Git Integration:
- In settings: shadowgraph.enableGitIntegration = true
- The watcher will auto-sync when .shadow/graph.jsonl changes
`;

    vscode.window.showInformationMessage(message, { modal: false });
    console.log('[ShadowGraph Git]', message);
}
