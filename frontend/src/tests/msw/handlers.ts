import { authHandlers } from './auth.handlers';
import { keysHandlers } from './keys.handlers';
import { wsHandlers } from './ws.handlers';
import { transcribeHandlers } from './transcribe.handlers';
import { accountHandlers } from './account.handlers';

export const handlers = [
  ...authHandlers,
  ...keysHandlers,
  ...wsHandlers,
  ...transcribeHandlers,
  ...accountHandlers,
];
