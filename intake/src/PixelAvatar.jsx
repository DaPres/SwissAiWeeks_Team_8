export default function PixelAvatar({ pixels, delay = 0 }) {
  return <span className="pixel-avatar" aria-hidden="true">
    <svg className="pixel-avatar-art" viewBox="0 0 8 8" fill="none" shapeRendering="crispEdges" focusable="false">
      {pixels.map(pixel => <rect key={`${pixel.x}:${pixel.y}`} x={pixel.x} y={pixel.y} width="1" height="1" fill={pixel.color}
        className="avatar-pixel" style={{ animationDelay: `${delay + pixel.delay}ms` }} />)}
    </svg>
  </span>;
}
