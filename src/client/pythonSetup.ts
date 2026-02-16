import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { execFile } from 'child_process';
import { promisify } from 'util';
import type { PythonInfo } from './types';

const execFileAsync = promisify(execFile);

export async function ensurePythonEnv(
    context: vscode.ExtensionContext
): Promise<PythonInfo> {
    const venvPath = path.join(context.globalStorageUri.fsPath, 'venv');
    const isWindows = process.platform === 'win32';
    const venvPython = isWindows
        ? path.join(venvPath, 'Scripts', 'python.exe')
        : path.join(venvPath, 'bin', 'python');

    console.log('[ShadowGraph] Checking venv at:', venvPath);
    console.log('[ShadowGraph] Expected venv Python:', venvPython);

    // Check if venv exists AND has dependencies installed
    let needsSetup = !fs.existsSync(venvPython);

    if (!needsSetup) {
        console.log('[ShadowGraph] Venv Python found, verifying dependencies...');
        try {
            const { stdout } = await execFileAsync(venvPython, ['-c', 'import tree_sitter_language_pack']);
            console.log('[ShadowGraph] Dependencies verified, venv is ready');
            return { pythonPath: venvPython, venvPath };
        } catch {
            console.log('[ShadowGraph] Dependencies missing, will reinstall...');
            needsSetup = true;
        }
    }

    if (!needsSetup) {
        return { pythonPath: venvPython, venvPath };
    }

    console.log('[ShadowGraph] Venv not found, creating new one...');
    const systemPython = await findPython();
    console.log('[ShadowGraph] System Python:', systemPython);

    await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: 'ShadowGraph: Setting up Python environment...',
            cancellable: false,
        },
        async (progress) => {
            try {
                progress.report({ message: 'Creating virtual environment...' });
                console.log('[ShadowGraph] Creating venv at:', venvPath);
                fs.mkdirSync(path.dirname(venvPath), { recursive: true });
                await execFileAsync(systemPython, ['-m', 'venv', venvPath]);
                console.log('[ShadowGraph] Venv created successfully');

                progress.report({ message: 'Installing dependencies...' });
                const reqPath = path.join(context.extensionUri.fsPath, 'requirements.txt');
                console.log('[ShadowGraph] Requirements file:', reqPath);
                console.log('[ShadowGraph] Requirements file exists:', fs.existsSync(reqPath));

                const { stderr, stdout } = await execFileAsync(venvPython, [
                    '-m',
                    'pip',
                    'install',
                    '-r',
                    reqPath,
                ]);

                console.log('[ShadowGraph] Pip install stdout:', stdout);
                if (stderr) {
                    console.log('[ShadowGraph] Pip install stderr:', stderr);
                }
                console.log('[ShadowGraph] Dependencies installed successfully');
            } catch (err) {
                console.error('[ShadowGraph] Error setting up venv:', err);
                throw new Error(`Failed to set up Python environment: ${err}`);
            }
        }
    );

    return { pythonPath: venvPython, venvPath };
}

async function findPython(): Promise<string> {
    const config = vscode.workspace.getConfiguration('shadowgraph');
    const configuredPath = config.get<string>('pythonPath');
    if (configuredPath) {
        return configuredPath;
    }

    const candidates =
        process.platform === 'win32'
            ? ['python', 'python3']
            : ['python3', 'python'];

    for (const cmd of candidates) {
        try {
            const { stdout } = await execFileAsync(cmd, ['--version']);
            const match = stdout.match(/Python (\d+)\.(\d+)/);
            if (match) {
                const major = parseInt(match[1], 10);
                const minor = parseInt(match[2], 10);
                if (major === 3 && minor >= 10) {
                    return cmd;
                }
            }
        } catch {
            // candidate not found, try next
        }
    }

    throw new Error(
        'ShadowGraph: No Python 3.10+ interpreter found. ' +
            'Please install Python 3.10+ or set shadowgraph.pythonPath in settings.'
    );
}
