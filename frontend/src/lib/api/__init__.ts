/**
 * API 包统一入口（路 3）。
 *
 * - safeCall：API 调用错误统一抛出 ApiError（带 code/message/original）
 * - useNotify：前端 toast + inline 两套错误反馈的统一 hook
 * - useApi：基于 useNotify 的 useApi hook，自动捕获 + 上报错误
 */
export * from './safeCall'
export * from './useNotify'
export * from './useApi'
