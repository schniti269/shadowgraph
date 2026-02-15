const esbuild = require('esbuild');
const fs = require('fs');
const path = require('path');

const production = process.argv.includes('--production');
const watch = process.argv.includes('--watch');

function copySqlWasm() {
    const src = path.join(__dirname, 'node_modules', 'sql.js', 'dist', 'sql-wasm.wasm');
    const dest = path.join(__dirname, 'dist', 'sql-wasm.wasm');
    fs.mkdirSync(path.join(__dirname, 'dist'), { recursive: true });
    if (fs.existsSync(src)) {
        fs.copyFileSync(src, dest);
    } else {
        console.warn('Warning: sql-wasm.wasm not found. Run npm install first.');
    }
}

async function main() {
    copySqlWasm();

    const ctx = await esbuild.context({
        entryPoints: ['src/client/extension.ts'],
        outfile: 'dist/extension.js',
        bundle: true,
        minify: production,
        sourcemap: !production,
        platform: 'node',
        target: 'node18',
        format: 'cjs',
        external: ['vscode'],
    });

    if (watch) {
        await ctx.watch();
        console.log('Watching for changes...');
    } else {
        await ctx.rebuild();
        await ctx.dispose();
        console.log('Build complete.');
    }
}

main().catch(e => {
    console.error(e);
    process.exit(1);
});
