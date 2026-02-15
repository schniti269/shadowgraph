export interface ThoughtRow {
    id: string;
    content: string;
    created_at?: string;  // ISO 8601 timestamp
}

export interface AnchorRow {
    node_id: string;
    file_path: string;
    symbol_name: string;
    ast_hash: string;
    start_line: number;
    status: 'VALID' | 'STALE';
}

export interface NodeRow {
    id: string;
    type: 'CODE_BLOCK' | 'THOUGHT' | 'REQUIREMENT';
    content: string;
    vector: Uint8Array | null;
}

export interface EdgeRow {
    source_id: string;
    target_id: string;
    relation: string;
}

export interface PythonInfo {
    pythonPath: string;
    venvPath: string;
}
