export type WorkRunPointer = { id: string; projectId: string; conversationId: string };
export interface WorkRunStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}
export declare function workRunStorageKey(accountId: string): string;
export declare function readWorkRun(storage: WorkRunStorage | null | undefined, accountId: string, now?: number): WorkRunPointer | null;
export declare function saveWorkRun(storage: WorkRunStorage | null | undefined, accountId: string, run: WorkRunPointer, now?: number): boolean;
export declare function clearWorkRun(storage: WorkRunStorage | null | undefined, accountId: string): void;
