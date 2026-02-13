import React from 'react';

const d = (size) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
});

export function IconGrid({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  );
}

export function IconNodes({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <circle cx="6" cy="6" r="3" />
      <circle cx="18" cy="18" r="3" />
      <path d="M8.5 8.5L15.5 15.5" />
      <circle cx="18" cy="6" r="3" />
      <path d="M15.5 8.5L8.5 15.5" />
      <circle cx="6" cy="18" r="3" />
    </svg>
  );
}

export function IconActivity({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

export function IconClock({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

export function IconShield({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <polyline points="9 12 11 14 15 10" />
    </svg>
  );
}

export function IconFile({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  );
}

export function IconAlert({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

export function IconChevronLeft({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

export function IconCheckCircle({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  );
}

export function IconXCircle({ size = 18 }) {
  return (
    <svg {...d(size)}>
      <circle cx="12" cy="12" r="10" />
      <line x1="15" y1="9" x2="9" y2="15" />
      <line x1="9" y1="9" x2="15" y2="15" />
    </svg>
  );
}
