export function AegisLogo({ size = 32 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="32" height="32" rx="8" fill="#059669" />
      {/* Stylised A letterform with evenodd cutout */}
      <path
        d="M16 8L22 25H19.5L18.5 22H13.5L12.5 25H10L16 8Z M16 12L18 21H14Z"
        fill="white"
        fillRule="evenodd"
      />
    </svg>
  )
}
