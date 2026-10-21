import { memo, useMemo, type CSSProperties } from 'react';
import { cssFamily, useFontsVersion } from '../model/fonts';
import { layoutText, resolveText, type TextLayout } from '../model/layout';
import type { Box, TextField, Values } from '../model/types';

export interface ResolvedField {
  text: string | null;
  layout: TextLayout | null;
}

// resolved text + layout for a field, redone when fonts finish loading
export function useFieldLayout(field: TextField, values: Values, box: Box = field.box, fontSize = field.style.fontSize): ResolvedField {
  const fontsVersion = useFontsVersion((s) => s.version);
  return useMemo(() => {
    const live = box === field.box && fontSize === field.style.fontSize ? field : { ...field, box, style: { ...field.style, fontSize }, fit: { ...field.fit, minFontSize: Math.min(field.fit.minFontSize * (fontSize / field.style.fontSize), fontSize) } };
    const text = resolveText(live, values);
    return { text, layout: text === null ? null : layoutText(text, live) };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [field, values, box, fontSize, fontsVersion]);
}

interface Props {
  field: TextField;
  layout: TextLayout;
  box: Box;
  style?: CSSProperties;
}

// text block in image px. has to match the Pillow renderer on the backend
export const FieldText = memo(function FieldText({ field, layout, box, style }: Props) {
  const s = field.style;
  return (
    <div
      aria-hidden
      style={{
        position: 'absolute',
        left: box.x,
        top: box.y,
        width: box.width,
        height: layout.boxHeight,
        pointerEvents: 'none',
        ...style,
      }}
    >
      <div style={{ position: 'absolute', left: 0, right: 0, top: layout.blockTop }}>
        {layout.lines.map((line, i) => (
          <div
            key={i}
            style={{
              height: layout.lineHeightPx,
              lineHeight: `${layout.lineHeightPx}px`,
              fontFamily: `${cssFamily(layout.familyId)}, sans-serif`,
              fontWeight: layout.weight,
              fontSize: layout.fontSize,
              letterSpacing: layout.letterSpacing ? `${layout.letterSpacing}em` : undefined,
              color: s.color,
              textAlign: s.align,
              whiteSpace: 'pre',
              textShadow: s.shadow ? `0 ${layout.fontSize * 0.04}px ${layout.fontSize * 0.12}px rgba(0,0,0,.45)` : undefined,
              fontKerning: 'normal',
            }}
          >
            {line}
          </div>
        ))}
      </div>
    </div>
  );
});
