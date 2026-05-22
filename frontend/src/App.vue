<script setup lang="ts">
import { darkTheme, themeOverrides } from './styles/theme'
import AppHeader from './components/layout/AppHeader.vue'
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <div class="app-layout">
            <AppHeader />
            <main class="app-main">
              <router-view />
            </main>
          </div>
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #app { height: 100%; }
body {
  background: #101014;
  color: rgba(255,255,255,0.82);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.app-layout { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
.app-main { flex: 1; padding: 24px; max-width: 1200px; margin: 0 auto; width: 100%; overflow-y: auto; }
</style>
