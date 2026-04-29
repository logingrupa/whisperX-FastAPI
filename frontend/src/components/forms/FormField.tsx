import type { ReactNode } from 'react';
import {
  FormField as RHFFormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import type { Control, FieldPath, FieldValues } from 'react-hook-form';

/**
 * DRY field-row used by Login + Register pages (UI-02 / UI-03 / UI-13).
 *
 * Wraps shadcn FormField + FormItem + FormLabel + FormControl + Input + FormMessage
 * into one reusable row — pages declare fields by name, label, and type only.
 *
 * `rightSlot` lets caller append a sibling node beneath the input but above the
 * error message (used by RegisterPage to render the password strength meter).
 */
export function FormFieldRow<T extends FieldValues>({
  control,
  name,
  label,
  type = 'text',
  autoComplete,
  placeholder,
  rightSlot,
}: {
  control: Control<T>;
  name: FieldPath<T>;
  label: string;
  type?: string;
  autoComplete?: string;
  placeholder?: string;
  rightSlot?: ReactNode;
}) {
  return (
    <RHFFormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              type={type}
              autoComplete={autoComplete}
              placeholder={placeholder}
              {...field}
              value={(field.value as string | undefined) ?? ''}
            />
          </FormControl>
          {rightSlot}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
