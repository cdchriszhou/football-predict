<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 120 120"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <circle cx="60" cy="60" r="58" fill="url(#fb-bg)" stroke="#2e7d32" stroke-width="2"/>
    <!-- Classic soccer ball panels -->
    <g transform="translate(60 60)">
      <polygon points="0,-22 6,-8 0,6 -6,-8" fill="#fff" stroke="#1a237e" stroke-width="1.2" stroke-linejoin="round"/>
      <polygon points="0,22 6,8 0,-6 -6,8" fill="#fff" stroke="#1a237e" stroke-width="1.2" stroke-linejoin="round"/>
      <polygon points="22,0 8,6 -6,0 8,-6" fill="#fff" stroke="#1a237e" stroke-width="1.2" stroke-linejoin="round"/>
      <polygon points="-22,0 -8,6 6,0 -8,-6" fill="#fff" stroke="#1a237e" stroke-width="1.2" stroke-linejoin="round"/>
      <polygon points="15,-15 8,-4 -4,-8 4,-18" fill="#f5f5f5" stroke="#1a237e" stroke-width="1" stroke-linejoin="round"/>
      <polygon points="-15,-15 -8,-4 4,-8 -4,-18" fill="#f5f5f5" stroke="#1a237e" stroke-width="1" stroke-linejoin="round"/>
      <polygon points="15,15 8,4 -4,8 4,18" fill="#f5f5f5" stroke="#1a237e" stroke-width="1" stroke-linejoin="round"/>
      <polygon points="-15,15 -8,4 4,8 -4,18" fill="#f5f5f5" stroke="#1a237e" stroke-width="1" stroke-linejoin="round"/>
    </g>
    <defs>
      <linearGradient id="fb-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#1b5e20"/>
        <stop offset="100%" stop-color="#2e7d32"/>
      </linearGradient>
    </defs>
  </svg>
</template>

<script setup>
defineProps({
  size: { type: [Number, String], default: 48 }
})
</script>
