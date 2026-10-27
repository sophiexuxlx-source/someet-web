/**
 * SoMeet AudioWorkletProcessor
 * Modern W3C Web Audio standard: runs audio buffer streaming off the main UI thread.
 * Captures raw 32-bit float audio frames with zero UI thread stutter.
 * Accumulates fixed 128-sample Web Audio quantums into 4096-sample chunks (~85ms)
 * before posting to the main thread. This prevents flooding the main UI thread event
 * loop with 375 IPC messages/sec and eliminates fractional downsampling phase jitter.
 */
class PcmWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 4096;
    this.buffer = new Float32Array(this.bufferSize);
    this.bytesWritten = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0 && input[0] && input[0].length > 0) {
      const channel = input[0];
      let offset = 0;
      while (offset < channel.length) {
        const toCopy = Math.min(channel.length - offset, this.bufferSize - this.bytesWritten);
        this.buffer.set(channel.subarray(offset, offset + toCopy), this.bytesWritten);
        this.bytesWritten += toCopy;
        offset += toCopy;

        if (this.bytesWritten >= this.bufferSize) {
          // Send a copy of the accumulated 4096-sample chunk (~85ms at 48kHz)
          this.port.postMessage(new Float32Array(this.buffer));
          this.bytesWritten = 0;
        }
      }
    }
    return true; // Keep processor alive
  }
}

registerProcessor('pcm-worklet-processor', PcmWorkletProcessor);
