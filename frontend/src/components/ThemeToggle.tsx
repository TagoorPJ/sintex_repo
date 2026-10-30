import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme, type ThemeMode } from '@/app/theme';
import { IconButton } from './ui/Button';
import { Menu, MenuItem } from './ui/Menu';

const OPTIONS: Array<{ mode: ThemeMode; label: string; Icon: typeof Sun }> = [
  { mode: 'light', label: 'Light', Icon: Sun },
  { mode: 'dark', label: 'Dark', Icon: Moon },
  { mode: 'system', label: 'System', Icon: Monitor },
];

export function ThemeToggle({ size = 'sm' }: { size?: 'sm' | 'md' }) {
  const mode = useTheme((s) => s.mode);
  const setMode = useTheme((s) => s.setMode);
  const Current = OPTIONS.find((o) => o.mode === mode)!.Icon;
  return (
    <Menu
      trigger={
        <IconButton label={`Theme: ${OPTIONS.find((o) => o.mode === mode)!.label}`} size={size}>
          <Current />
        </IconButton>
      }
    >
      {OPTIONS.map(({ mode: m, label, Icon }) => (
        <MenuItem key={m} icon={<Icon />} hint={m === mode ? '✓' : undefined} onClick={() => setMode(m)}>
          {label}
        </MenuItem>
      ))}
    </Menu>
  );
}
