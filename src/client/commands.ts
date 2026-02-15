import * as vscode from 'vscode';
import * as path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';
import { ShadowDatabase } from './database';
import { ShadowCodeLensProvider } from './codelens';
import { StaleDecorationManager } from './decorations';
import type { PythonInfo } from './types';

const execFileAsync = promisify(execFile);

export function registerCommands(
    context: vscode.ExtensionContext,
    db: ShadowDatabase,
    pythonInfo: PythonInfo,
    codeLensProvider: ShadowCodeLensProvider,
    staleManager: StaleDecorationManager
): void {
    const serverScript = path.join(
        context.extensionPath,
        'src',
        'server',
        'main.py'
    );

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    const dbPath = workspaceFolder
        ? path.join(workspaceFolder.uri.fsPath, '.vscode', 'shadow.db')
        : '';

    // Initialize database
    context.subscriptions.push(
        vscode.commands.registerCommand('shadowgraph.initialize', async () => {
            db.reload();
            vscode.window.showInformationMessage(
                'ShadowGraph: Database initialized.'
            );
        })
    );

    // Index current file
    context.subscriptions.push(
        vscode.commands.registerCommand(
            'shadowgraph.indexCurrentFile',
            async () => {
                const editor = vscode.window.activeTextEditor;
                if (!editor) {
                    vscode.window.showWarningMessage(
                        'ShadowGraph: No active file to index.'
                    );
                    return;
                }

                const filePath = editor.document.uri.fsPath;

                try {
                    const { stdout } = await execFileAsync(
                        pythonInfo.pythonPath,
                        [serverScript, '--cli', 'index_file', filePath],
                        {
                            cwd: workspaceFolder?.uri.fsPath,
                            env: {
                                ...process.env,
                                SHADOW_DB_PATH: dbPath,
                                PYTHONDONTWRITEBYTECODE: '1',
                            },
                        }
                    );

                    const result = JSON.parse(stdout);
                    vscode.window.showInformationMessage(
                        `ShadowGraph: Indexed ${result.symbols_indexed} symbol(s) in ${result.file}`
                    );

                    db.reload();
                    codeLensProvider.refresh();
                    staleManager.refresh();
                } catch (err) {
                    vscode.window.showErrorMessage(
                        `ShadowGraph: Index failed: ${err}`
                    );
                }
            }
        )
    );

    // Check drift
    context.subscriptions.push(
        vscode.commands.registerCommand('shadowgraph.checkDrift', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage(
                    'ShadowGraph: No active file to check.'
                );
                return;
            }

            const filePath = editor.document.uri.fsPath;

            try {
                const { stdout } = await execFileAsync(
                    pythonInfo.pythonPath,
                    [serverScript, '--cli', 'check_drift', filePath],
                    {
                        cwd: workspaceFolder?.uri.fsPath,
                        env: {
                            ...process.env,
                            SHADOW_DB_PATH: dbPath,
                            PYTHONDONTWRITEBYTECODE: '1',
                        },
                    }
                );

                const result = JSON.parse(stdout);
                if (result.stale_count === 0) {
                    vscode.window.showInformationMessage(
                        'ShadowGraph: All anchors are up to date.'
                    );
                } else {
                    vscode.window.showWarningMessage(
                        `ShadowGraph: ${result.stale_count} stale anchor(s) detected.`
                    );
                }

                db.reload();
                codeLensProvider.refresh();
                staleManager.refresh();
            } catch (err) {
                vscode.window.showErrorMessage(
                    `ShadowGraph: Drift check failed: ${err}`
                );
            }
        })
    );

    // Show thoughts for a symbol
    context.subscriptions.push(
        vscode.commands.registerCommand(
            'shadowgraph.showThoughts',
            async (filePath?: string, symbolName?: string) => {
                if (!filePath || !symbolName) {
                    const editor = vscode.window.activeTextEditor;
                    if (!editor) {
                        return;
                    }
                    filePath =
                        filePath ||
                        vscode.workspace.asRelativePath(editor.document.uri);

                    const symbols = db.getSymbolNames(filePath);
                    if (symbols.length === 0) {
                        vscode.window.showInformationMessage(
                            'ShadowGraph: No indexed symbols in this file. Run "Index Current File" first.'
                        );
                        return;
                    }

                    symbolName = await vscode.window.showQuickPick(symbols, {
                        placeHolder: 'Select a symbol to view thoughts',
                    });
                    if (!symbolName) {
                        return;
                    }
                }

                const thoughts = db.getThoughtsForSymbol(filePath, symbolName);
                if (thoughts.length === 0) {
                    vscode.window.showInformationMessage(
                        `ShadowGraph: No thoughts linked to ${symbolName}`
                    );
                    return;
                }

                const output = vscode.window.createOutputChannel(
                    'ShadowGraph Thoughts',
                    'markdown'
                );
                output.clear();
                output.appendLine(`# Thoughts for \`${symbolName}\``);
                output.appendLine(`**File:** ${filePath}\n`);
                for (const thought of thoughts) {
                    output.appendLine(`---`);
                    output.appendLine(`**ID:** \`${thought.id}\``);
                    if (thought.created_at) {
                        const date = new Date(thought.created_at);
                        output.appendLine(`**Created:** ${date.toLocaleString()}`);
                    }
                    output.appendLine(`\n${thought.content}\n`);
                }
                output.show(true);
            }
        )
    );

    // Add thought to a symbol
    context.subscriptions.push(
        vscode.commands.registerCommand(
            'shadowgraph.addThought',
            async () => {
                const editor = vscode.window.activeTextEditor;
                if (!editor) {
                    vscode.window.showWarningMessage(
                        'ShadowGraph: No active file.'
                    );
                    return;
                }

                const filePath = vscode.workspace.asRelativePath(
                    editor.document.uri
                );
                const symbols = db.getSymbolNames(filePath);

                if (symbols.length === 0) {
                    vscode.window.showInformationMessage(
                        'ShadowGraph: No indexed symbols in this file. Run "Index Current File" first.'
                    );
                    return;
                }

                const symbolName = await vscode.window.showQuickPick(symbols, {
                    placeHolder: 'Select a symbol to attach thought to',
                });
                if (!symbolName) {
                    return;
                }

                const thoughtText = await vscode.window.showInputBox({
                    prompt: `Add a thought to ${symbolName}`,
                    placeHolder: 'Enter your thought, note, or requirement...',
                });
                if (!thoughtText) {
                    return;
                }

                try {
                    const thoughtId = db.addThought(
                        filePath,
                        symbolName,
                        thoughtText
                    );
                    vscode.window.showInformationMessage(
                        `ShadowGraph: Thought added (${thoughtId})`
                    );
                    codeLensProvider.refresh();
                } catch (err) {
                    vscode.window.showErrorMessage(
                        `ShadowGraph: Failed to add thought: ${err}`
                    );
                }
            }
        )
    );

    // Show server status and debug info
    context.subscriptions.push(
        vscode.commands.registerCommand(
            'shadowgraph.showStatus',
            async () => {
                const output = vscode.window.createOutputChannel(
                    'ShadowGraph Status',
                    'markdown'
                );
                output.clear();

                output.appendLine('# ShadowGraph Status\n');
                output.appendLine(
                    `**Python Path:** ${pythonInfo.pythonPath}`
                );
                output.appendLine(`**Database Path:** ${dbPath}`);
                output.appendLine(
                    `**Workspace:** ${workspaceFolder?.uri.fsPath || 'None'}`
                );
                output.appendLine('\n## MCP Server\n');
                output.appendLine(
                    'Check the browser DevTools console for MCP connection logs.'
                );
                output.appendLine('\n**To debug:**');
                output.appendLine(
                    '1. Open VS Code Dev Tools: `Ctrl+Shift+I`'
                );
                output.appendLine(
                    '2. Go to Console tab'
                );
                output.appendLine(
                    '3. Look for messages starting with "[ShadowGraph]"'
                );
                output.appendLine('\n## Troubleshooting\n');
                output.appendLine(
                    '- Ensure Python 3.10+ is installed: `python --version`'
                );
                output.appendLine(`- Check database exists: ${dbPath}`);
                output.appendLine(
                    '- Review extension logs in VS Code Output panel'
                );

                output.show(true);
            }
        )
    );

    // Run diagnostics
    context.subscriptions.push(
        vscode.commands.registerCommand(
            'shadowgraph.runDiagnostics',
            async () => {
                const output = vscode.window.createOutputChannel(
                    'ShadowGraph Diagnostics',
                    'markdown'
                );
                output.clear();

                output.appendLine('# ShadowGraph Diagnostics\n');

                // Check Python
                try {
                    const { stdout } = await execFileAsync(
                        pythonInfo.pythonPath,
                        ['--version']
                    );
                    output.appendLine(`✓ Python: ${stdout.trim()}`);
                } catch {
                    output.appendLine('✗ Python: Failed to execute');
                }

                // Check database
                output.appendLine(`✓ Database path: ${dbPath}`);
                const fs = require('fs');
                const dbExists = fs.existsSync(dbPath);
                output.appendLine(
                    `${dbExists ? '✓' : '✗'} Database file exists`
                );

                // Check required modules
                try {
                    await execFileAsync(pythonInfo.pythonPath, [
                        '-c',
                        'import mcp, tree_sitter_language_pack; print("OK")',
                    ]);
                    output.appendLine(
                        '✓ Required Python packages installed'
                    );
                } catch {
                    output.appendLine('✗ Missing required packages');
                    output.appendLine(
                        'Run: `pip install -r requirements.txt`'
                    );
                }

                output.appendLine('\n**Next steps if diagnostics fail:**');
                output.appendLine(
                    '1. Check workspace folder is open'
                );
                output.appendLine(
                    '2. Install dependencies: `pip install -r requirements.txt`'
                );
                output.appendLine(
                    '3. Reload VS Code window: Ctrl+R'
                );
                output.appendLine(
                    '4. Check "Output" panel > "ShadowGraph" channel'
                );

                output.show(true);
            }
        )
    );
}
