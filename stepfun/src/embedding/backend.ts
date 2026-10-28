import { env } from '@huggingface/transformers';
import type { BackendCandidate, BackendStatus, Dtype } from '../types';

export const MODEL_ID = 'bge-small-zh-v1.5';
export const MODEL_DIMENSION = 512;
export const MODEL_LABEL = 'BAAI/bge-small-zh-v1.5（ONNX 转换版）';

const DTYPE_LABEL: Record<Dtype, string> = {
  fp32: 'FP32',
  fp16: 'FP16',
  q8: 'INT8',
};

export function dtypeLabel(dtype: Dtype): string {
  return DTYPE_LABEL[dtype];
}

export function configureLocalEnv(): void {
  env.allowLocalModels = true;
  env.allowRemoteModels = false;
  env.localModelPath = '/models/';
  env.useBrowserCache = false;
  const ortEnv = env.backends.onnx as any;
  if (ortEnv?.wasm) ortEnv.wasm.wasmPaths = '/ort/';
}

export interface WebGpuState {
  available: boolean;
  forced: boolean;
  reason: string;
}

export async function detectWebGpu(): Promise<WebGpuState> {
  const forced = new URLSearchParams(window.location.search).get('backend') === 'wasm';
  if (forced) {
    return { available: false, forced: true, reason: 'URL 参数 backend=wasm 强制使用 WASM' };
  }
  const gpu = (navigator as any).gpu;
  if (!gpu?.requestAdapter) {
    return { available: false, forced: false, reason: '当前浏览器未暴露 navigator.gpu' };
  }
  try {
    const adapter = await gpu.requestAdapter();
    if (!adapter) {
      return { available: false, forced: false, reason: 'WebGPU 适配器不可用' };
    }
    let detail = '';
    try {
      const info = adapter.info ?? (await adapter.requestAdapterInfo?.()) ?? {};
      detail = [info.vendor, info.architecture, info.description].filter(Boolean).join(' ');
    } catch {
      detail = '';
    }
    return { available: true, forced: false, reason: detail ? `检测到 ${detail}` : '检测到 WebGPU 适配器' };
  } catch (error) {
    return { available: false, forced: false, reason: `WebGPU 初始化失败：${(error as Error).message}` };
  }
}

export function candidateChain(webgpu: WebGpuState): BackendCandidate[] {
  if (webgpu.forced || !webgpu.available) return [{ device: 'wasm', dtype: 'q8' }];
  return [
    { device: 'webgpu', dtype: 'fp16' },
    { device: 'webgpu', dtype: 'q8' },
    { device: 'wasm', dtype: 'q8' },
  ];
}

export function describeCandidate(candidate: BackendCandidate): string {
  return `${candidate.device === 'webgpu' ? 'WebGPU' : 'WASM'} · ${dtypeLabel(candidate.dtype)}`;
}

export function statusFrom(
  chosen: BackendCandidate,
  webgpu: WebGpuState,
  attempts: BackendStatus['attempts'],
  loadMs: number,
  warmupMs: number,
): BackendStatus {
  const failed = attempts.filter((attempt) => !attempt.ok);
  let reason = webgpu.reason;
  if (chosen.device === 'wasm' && webgpu.available && failed.length) {
    reason = `WebGPU 不可用，已自动降级 WASM（${failed[0].error ?? '加载失败'}）`;
  } else if (chosen.device === 'wasm' && webgpu.available) {
    reason = 'WebGPU 探测失败，使用 WASM';
  }
  return {
    backend: chosen.device,
    dtype: chosen.dtype,
    label: describeCandidate(chosen),
    reason,
    webgpuDetected: webgpu.available,
    forcedWasm: webgpu.forced,
    attempts,
    loadMs,
    warmupMs,
  } as BackendStatus;
}
