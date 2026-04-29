/**
 * Single source of truth for login/register form schemas (DRY — UI-02, UI-03).
 *
 * Backend mirrors:
 *   - email: pydantic EmailStr
 *   - password: 8-128 chars (register), 1-128 chars (login)
 *
 * Register-only:
 *   - confirmPassword: must match password
 *   - termsAccepted: boolean — must be true to enable submit
 */

import { z } from 'zod';

export const loginSchema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z.string().min(1, 'Password is required').max(128),
});

export const registerSchema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .max(128, 'Password is too long'),
  confirmPassword: z.string(),
  termsAccepted: z
    .boolean()
    .refine((v) => v === true, 'You must accept the terms to continue'),
}).refine((data) => data.password === data.confirmPassword, {
  path: ['confirmPassword'],
  message: 'Passwords do not match',
});

export type LoginInput = z.infer<typeof loginSchema>;
export type RegisterInput = z.infer<typeof registerSchema>;
