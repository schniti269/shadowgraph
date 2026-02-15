import * as vscode from 'vscode';
import * as path from 'path';
import { ShadowDatabase } from './database';

export class StaleDecorationManager implements vscode.Disposable {
    private decorationType: vscode.TextEditorDecorationType;
    private disposables: vscode.Disposable[] = [];

    constructor(
        context: vscode.ExtensionContext,
        private db: ShadowDatabase
    ) {
        this.decorationType = vscode.window.createTextEditorDecorationType({
            gutterIconPath: vscode.Uri.file(
                path.join(context.extensionPath, 'icons', 'stale.svg')
            ),
            gutterIconSize: 'contain',
            overviewRulerColor: 'rgba(255, 165, 0, 0.8)',
            overviewRulerLane: vscode.OverviewRulerLane.Right,
        });

        this.disposables.push(
            vscode.window.onDidChangeActiveTextEditor(() => this.refresh()),
            vscode.workspace.onDidOpenTextDocument(() => this.refresh())
        );

        this.refresh();
    }

    refresh(): void {
        const config = vscode.workspace.getConfiguration('shadowgraph');
        if (!config.get<boolean>('enableStaleDecorations', true)) {
            const editor = vscode.window.activeTextEditor;
            if (editor) {
                editor.setDecorations(this.decorationType, []);
            }
            return;
        }

        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            return;
        }

        const relativePath = vscode.workspace.asRelativePath(editor.document.uri);
        const staleAnchors = this.db.getStaleAnchors(relativePath);

        const decorations: vscode.DecorationOptions[] = staleAnchors.map(
            (anchor) => {
                const line = Math.max(0, (anchor.start_line ?? 1) - 1);
                return {
                    range: new vscode.Range(line, 0, line, 0),
                    hoverMessage: new vscode.MarkdownString(
                        `**ShadowGraph:** Code at \`${anchor.symbol_name}\` has changed since last indexing. Linked thoughts may be stale.`
                    ),
                };
            }
        );

        editor.setDecorations(this.decorationType, decorations);
    }

    dispose(): void {
        this.decorationType.dispose();
        this.disposables.forEach((d) => d.dispose());
    }
}
