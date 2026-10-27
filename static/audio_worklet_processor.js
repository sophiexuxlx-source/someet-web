/**
 * SoMeet AudioWorkletProcessor
 * Modern W3C Web Audio standard: runs audio buffer streaming off the main UI thread.
 * Captures raw 32-bit float audio frames with zero UI thread stutter.
 */
class PcmWorkletProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0 && input[0] && input[0].length > 0) {
      // Send a copy of the Float32Array channel data to the main thread
      this.port.postMessage(input[0]);
    }
    return true; // Keep processor alive
  }
}

registerProcessor('pcm-worklet-processor', PcmWorkletProcessor);
