import * as vscode from 'vscode';
import { ShadowDatabase } from './database';

const SYMBOL_PATTERNS: Record<string, RegExp> = {
    python: /^\s*(?:def|class)\s+(\w+)/gm,
    typescript: /^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+(\w+)/gm,
    typescriptreact: /^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+(\w+)/gm,
    javascript: /^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+(\w+)/gm,
    javascriptreact: /^\s*(?:export\s+)?(?:async\s+)?(?:function|class)\s+(\w+)/gm,
};

const PREFIX_MAP: Record<string, string> = {
    def: 'function',
    function: 'function',
    class: 'class',
};

export class ShadowCodeLensProvider implements vscode.CodeLensProvider {
    private _onDidChangeCodeLenses = new vscode.EventEmitter<void>();
    readonly onDidChangeCodeLenses = this._onDidChangeCodeLenses.event;

    constructor(private db: ShadowDatabase) {}

    refresh(): void {
        this._onDidChangeCodeLenses.fire();
    }

    provideCodeLenses(
        document: vscode.TextDocument,
        _token: vscode.CancellationToken
    ): vscode.CodeLens[] {
        const config = vscode.workspace.getConfiguration('shadowgraph');
        if (!config.get<boolean>('enableCodeLens', true)) {
            return [];
        }

        const pattern = SYMBOL_PATTERNS[document.languageId];
        if (!pattern) {
            return [];
        }

        const text = document.getText();
        const relativePath = vscode.workspace.asRelativePath(document.uri);
        const lenses: vscode.CodeLens[] = [];

        // Reset regex state
        pattern.lastIndex = 0;
        let match: RegExpExecArray | null;

        while ((match = pattern.exec(text)) !== null) {
            const symbolName = match[1];
            const line = document.positionAt(match.index).line;
            const range = new vscode.Range(line, 0, line, 0);

            // Determine prefix (function vs class) from the keyword
            const keyword = match[0].trim().split(/\s+/).find(
                (w) => w === 'def' || w === 'function' || w === 'class'
            );
            const prefix = PREFIX_MAP[keyword || 'function'] || 'function';
            const fullSymbolName = `${prefix}:${symbolName}`;

            const thoughts = this.db.getThoughtsForSymbol(
                relativePath,
                fullSymbolName
            );

            if (thoughts.length > 0) {
                lenses.push(
                    new vscode.CodeLens(range, {
                        title: `$(lightbulb) ${thoughts.length} thought${thoughts.length > 1 ? 's' : ''}`,
                        command: 'shadowgraph.showThoughts',
                        arguments: [relativePath, fullSymbolName],
                    })
                );
            }
        }

        return lenses;
    }
}
