import * as vscode from 'vscode';
import * as path from 'path';
import { ensurePythonEnv } from './pythonSetup';
import { ShadowDatabase } from './database';
import { ShadowCodeLensProvider } from './codelens';
import { StaleDecorationManager } from './decorations';
import { registerCommands } from './commands';

export async function activate(context: vscode.ExtensionContext) {
    console.log('[ShadowGraph] Extension activation started');

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
        console.log('[ShadowGraph] No workspace folder open');
        return;
    }

    console.log('[ShadowGraph] Workspace:', workspaceFolder.uri.fsPath);

    const dbPath = path.join(
        workspaceFolder.uri.fsPath,
        '.vscode',
        'shadow.db'
    );

    // Initialize the sql.js database reader
    const db = new ShadowDatabase(context, dbPath);
    try {
        console.log('[ShadowGraph] Initializing database at:', dbPath);
        await db.initialize();
        console.log('[ShadowGraph] Database initialized successfully');
    } catch (err) {
        console.error('[ShadowGraph] Database initialization failed:', err);
        vscode.window.showErrorMessage(
            `ShadowGraph: Failed to initialize database: ${err}`
        );
        return;
    }

    // Set up Python environment (venv + pip install)
    let pythonInfo;
    try {
        console.log('[ShadowGraph] Ensuring Python environment...');
        pythonInfo = await ensurePythonEnv(context);
        console.log('[ShadowGraph] Python path:', pythonInfo.pythonPath);
    } catch (err) {
        console.error('[ShadowGraph] Python setup failed:', err);
        vscode.window.showErrorMessage(`${err}`);
        return;
    }

    // CRITICAL: Use absolute path via extensionUri, not relative path
    const serverScript = vscode.Uri.joinPath(
        context.extensionUri,
        'src',
        'server',
        'main.py'
    ).fsPath;

    console.log('[ShadowGraph] Server script path:', serverScript);
    console.log('[ShadowGraph] Python executable:', pythonInfo.pythonPath);

    // Register MCP server definition provider with POSITIONAL ARGUMENTS
    context.subscriptions.push(
        vscode.lm.registerMcpServerDefinitionProvider(
            'shadowgraph.mcpServer',
            {
                provideMcpServerDefinitions: async () => {
                    console.log('[ShadowGraph] Copilot is asking for tools...');

                    try {
                        // FIX: Use positional arguments, not options object
                        // Arg 1: Label (string)
                        // Arg 2: Command (string)
                        // Arg 3: Args (string[])
                        // Arg 4: Options (environment variables, etc.)
                        const server = new vscode.McpStdioServerDefinition(
                            'ShadowGraph Tools',  // Label
                            pythonInfo.pythonPath,  // Command
                            [serverScript],  // Args
                            {  // Options
                                env: {
                                    SHADOW_DB_PATH: dbPath,
                                    PYTHONDONTWRITEBYTECODE: '1',
                                    PYTHONPATH: path.join(context.extensionPath, 'src', 'server'),
                                },
                            }
                        );

                        console.log('[ShadowGraph] MCP definition created successfully');
                        return [server];
                    } catch (err) {
                        console.error('[ShadowGraph] Error creating MCP definition:', err);
                        throw err;
                    }
                },
            }
        )
    );

    console.log('[ShadowGraph] MCP provider registered');

    // Register CodeLens provider
    const codeLensProvider = new ShadowCodeLensProvider(db);
    context.subscriptions.push(
        vscode.languages.registerCodeLensProvider(
            [
                { scheme: 'file', language: 'python' },
                { scheme: 'file', language: 'typescript' },
                { scheme: 'file', language: 'javascript' },
                { scheme: 'file', language: 'typescriptreact' },
                { scheme: 'file', language: 'javascriptreact' },
            ],
            codeLensProvider
        )
    );

    // Register gutter decorations for stale anchors
    const staleManager = new StaleDecorationManager(context, db);
    context.subscriptions.push(staleManager);

    // Register commands
    registerCommands(context, db, pythonInfo, codeLensProvider, staleManager);

    // Watch shadow.db for changes (Python server writes trigger UI refresh)
    const watcher = vscode.workspace.createFileSystemWatcher(
        new vscode.RelativePattern(workspaceFolder, '.vscode/shadow.db')
    );
    watcher.onDidChange(() => {
        db.reload();
        codeLensProvider.refresh();
        staleManager.refresh();
    });
    watcher.onDidCreate(() => {
        db.reload();
        codeLensProvider.refresh();
        staleManager.refresh();
    });
    context.subscriptions.push(watcher);
}

export function deactivate() {}
