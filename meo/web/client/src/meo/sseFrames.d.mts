export declare const MAX_STREAM_BUFFER_CHARS: number;
export declare function takeSseFrames(
  input: string, flush?: boolean
): { frames: Array<{ event: string; data: string }>; remainder: string };
