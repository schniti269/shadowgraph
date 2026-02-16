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

    if (fs.existsSync(venvPython)) {
        return { pythonPath: venvPython, venvPath };
    }

    const systemPython = await findPython();

    await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: 'ShadowGraph: Setting up Python environment...',
            cancellable: false,
        },
        async (progress) => {
            progress.report({ message: 'Creating virtual environment...' });
            fs.mkdirSync(path.dirname(venvPath), { recursive: true });
            await execFileAsync(systemPython, ['-m', 'venv', venvPath]);

            progress.report({ message: 'Installing dependencies...' });
            const reqPath = path.join(context.extensionUri.fsPath, 'requirements.txt');
            await execFileAsync(venvPython, [
                '-m',
                'pip',
                'install',
                '--quiet',
                '-r',
                reqPath,
            ]);
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
