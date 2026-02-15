import * as vscode from 'vscode';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import * as net from 'net';

let serverProcess: ChildProcess | null = null;
const SERVER_PORT = 3000;
const SERVER_HOST = '127.0.0.1';

export function activate(context: vscode.ExtensionContext) {
    const serverId = 'shadow-graph-server';
    const serverPath = context.asAbsolutePath(path.join('dist', 'server.js'));

    console.log('[Shadow Graph] Starting MCP server process...');
    serverProcess = spawn('node', [serverPath], {
        stdio: ['ignore', 'ignore', 'ignore'],
        detached: true,
        env: {
            ...process.env,
            "ROOT_PATH": vscode.workspace.workspaceFolders?.[0].uri.fsPath || ""
        }
    });

    serverProcess.unref(); // Don't wait for this process

    // Wait for server to be ready
    setTimeout(() => {
        testServerConnection();
    }, 1000);

    // Cleanup: Kill server on deactivate
    context.subscriptions.push(
        new vscode.Disposable(() => {
            if (serverProcess) {
                console.log('[Shadow Graph] Stopping server...');
                try {
                    process.kill(-serverProcess.pid!);
                } catch (e) {
                    console.log('[Shadow Graph] Server already stopped');
                }
            }
        })
    );

    vscode.window.showInformationMessage(`Shadow Graph MCP Server running on ${SERVER_HOST}:${SERVER_PORT}`);
    console.log(`[Shadow Graph] Extension activated - server hosting on port ${SERVER_PORT}`);
}

function testServerConnection() {
    const socket = net.createConnection(SERVER_PORT, SERVER_HOST, () => {
        console.log('[Shadow Graph] ✓ Server connection verified');
        socket.end();
    });

    socket.on('error', (err) => {
        console.log('[Shadow Graph] Server not yet ready:', err.message);
    });
}

export function deactivate() {
    if (serverProcess) {
        try {
            process.kill(-serverProcess.pid!);
        } catch (e) {
            // Process already dead
        }
    }
}
