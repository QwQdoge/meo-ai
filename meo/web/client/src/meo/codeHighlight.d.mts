export declare const MAX_HIGHLIGHT_CHARS: number;
export type CodeToken = { text: string; kind: 'plain' | 'comment' | 'string' | 'number' | 'keyword' | 'variable' };
export declare function tokenizeCode(code: string, language?: string | null): CodeToken[];
