import styled from "styled-components";

const TypewriterLoader = () => (
  <StyledWrapper role="status" aria-label="Analyzing email">
    <div className="typewriter" aria-hidden="true">
      <div className="slide"><i /></div>
      <div className="paper" />
      <div className="keyboard" />
    </div>
    <span className="sr-only">Analyzing email...</span>
  </StyledWrapper>
);

const StyledWrapper = styled.div`
  --tw-blue: var(--color-accent);
  --tw-blue-dark: var(--color-accent-dark);
  --tw-key: var(--color-surface);
  --tw-paper: var(--color-bone);
  --tw-text: var(--color-border-dotted);
  --tw-tool: var(--color-warning);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 118px;
  width: 150px;
  color: var(--color-ink);

  .typewriter {
    --duration: 3s;
    position: relative;
    animation: bounce05 var(--duration) linear infinite;
  }

  .typewriter .slide {
    width: 92px;
    height: 20px;
    margin-left: 14px;
    border-radius: 3px;
    transform: translateX(14px);
    background: linear-gradient(var(--tw-blue), var(--tw-blue-dark));
    animation: slide05 var(--duration) ease infinite;
  }

  .typewriter .slide::before,
  .typewriter .slide::after,
  .typewriter .slide i::before {
    content: "";
    position: absolute;
    background: var(--tw-tool);
  }

  .typewriter .slide::before {
    top: 6px;
    left: 100%;
    width: 2px;
    height: 8px;
  }

  .typewriter .slide::after {
    top: 3px;
    left: 94px;
    width: 6px;
    height: 14px;
    border-radius: 3px;
  }

  .typewriter .slide i {
    display: block;
    position: absolute;
    top: 4px;
    right: 100%;
    width: 6px;
    height: 4px;
    background: var(--tw-tool);
  }

  .typewriter .slide i::before {
    top: -2px;
    right: 100%;
    width: 4px;
    height: 14px;
    border-radius: 2px;
  }

  .typewriter .paper {
    position: absolute;
    top: -26px;
    left: 24px;
    width: 40px;
    height: 46px;
    border-radius: 5px;
    background: var(--tw-paper);
    transform: translateY(46px);
    animation: paper05 var(--duration) linear infinite;
  }

  .typewriter .paper::before {
    content: "";
    position: absolute;
    top: 7px;
    left: 6px;
    right: 6px;
    height: 4px;
    border-radius: 2px;
    transform: scaleY(0.8);
    background: var(--tw-text);
    box-shadow: 0 12px 0 var(--tw-text), 0 24px 0 var(--tw-text), 0 36px 0 var(--tw-text);
  }

  .typewriter .keyboard {
    position: relative;
    z-index: 1;
    width: 120px;
    height: 56px;
    margin-top: -10px;
  }

  .typewriter .keyboard::before,
  .typewriter .keyboard::after {
    content: "";
    position: absolute;
  }

  .typewriter .keyboard::before {
    inset: 0;
    border-radius: 7px;
    background: linear-gradient(135deg, var(--tw-blue), var(--tw-blue-dark));
    transform: perspective(10px) rotateX(2deg);
    transform-origin: 50% 100%;
  }

  .typewriter .keyboard::after {
    top: 25px;
    left: 2px;
    width: 11px;
    height: 4px;
    border-radius: 2px;
    background: var(--tw-key);
    box-shadow: 15px 0 var(--tw-key), 30px 0 var(--tw-key), 45px 0 var(--tw-key), 60px 0 var(--tw-key), 75px 0 var(--tw-key), 90px 0 var(--tw-key), 22px 10px var(--tw-key), 37px 10px var(--tw-key), 52px 10px var(--tw-key), 60px 10px var(--tw-key), 68px 10px var(--tw-key), 83px 10px var(--tw-key);
    animation: keyboard05 var(--duration) linear infinite;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  @keyframes bounce05 {
    85%, 92%, 100% { transform: translateY(0); }
    89% { transform: translateY(-4px); }
    95% { transform: translateY(2px); }
  }

  @keyframes slide05 {
    5% { transform: translateX(14px); }
    15%, 30% { transform: translateX(6px); }
    40%, 55% { transform: translateX(0); }
    65%, 70% { transform: translateX(-4px); }
    80%, 89% { transform: translateX(-12px); }
    100% { transform: translateX(14px); }
  }

  @keyframes paper05 {
    5% { transform: translateY(46px); }
    20%, 30% { transform: translateY(34px); }
    40%, 55% { transform: translateY(22px); }
    65%, 70% { transform: translateY(10px); }
    80%, 85% { transform: translateY(0); }
    92%, 100% { transform: translateY(46px); }
  }

  @keyframes keyboard05 {
    5%, 12%, 21%, 30%, 39%, 48%, 57%, 66%, 75%, 84% {
      transform: translateY(0);
    }
    9%, 18%, 27%, 36%, 45%, 54%, 63%, 72%, 81% {
      transform: translateY(2px);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .typewriter,
    .typewriter .slide,
    .typewriter .paper,
    .typewriter .keyboard::after {
      animation-play-state: paused;
    }
  }
`;

export default TypewriterLoader;
