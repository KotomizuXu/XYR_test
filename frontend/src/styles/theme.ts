import { darkTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'

export const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#36ad6a',
    primaryColorHover: '#5acea0',
    primaryColorPressed: '#2d9460',
    borderRadius: '8px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  },
  Card: {
    borderRadius: '12px',
  },
}

export { darkTheme }
