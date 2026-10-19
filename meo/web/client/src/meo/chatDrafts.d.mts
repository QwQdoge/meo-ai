export declare function chatDraftKey(accountId: string | null | undefined, conversationId: string): string | null;
export declare function readChatDraft(storage: Storage | null, accountId: string | null | undefined, conversationId: string): string;
export declare function writeChatDraft(storage: Storage | null, accountId: string | null | undefined, conversationId: string, value: string): boolean;
