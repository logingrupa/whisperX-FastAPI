import { authHandlers } from './auth.handlers';
import { keysHandlers } from './keys.handlers';
import { wsHandlers } from './ws.handlers';
import { transcribeHandlers } from './transcribe.handlers';

export const handlers = [
  ...authHandlers,
  ...keysHandlers,
  ...wsHandlers,
  ...transcribeHandlers,
];
