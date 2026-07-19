'use client';
import type { ReactNode } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { cn } from '@/lib/utils';

const CIRCUITS = [
  'M 50 100 L 200 100 L 200 200 L 350 200 L 350 300 L 500 300',
  'M 500 50 L 500 150 L 650 150 L 650 250 L 800 250 L 800 350',
  'M 100 400 L 250 400 L 250 500 L 400 500 L 400 600 L 550 600',
  'M 600 400 L 750 400 L 750 500 L 900 500 L 900 600',
  'M 50 300 L 150 300 L 150 450 L 300 450 L 300 550',
  'M 700 100 L 850 100 L 850 200 L 950 200',
  'M 150 200 L 300 200 L 300 350 L 450 350 L 450 450',
  'M 550 150 L 700 150 L 700 300 L 850 300',
];

const NODES = [
  { x: 200, y: 100 },
  { x: 350, y: 200 },
  { x: 500, y: 300 },
  { x: 500, y: 150 },
  { x: 650, y: 150 },
  { x: 800, y: 350 },
  { x: 250, y: 400 },
  { x: 400, y: 500 },
  { x: 750, y: 400 },
  { x: 150, y: 300 },
  { x: 300, y: 450 },
  { x: 850, y: 100 },
];

export const BackgroundPaths = ({
  children,
  className,
  svgOptions,
}: {
  children: ReactNode;
  className?: string;
  svgOptions?: {
    duration?: number;
  };
}) => {
  return (
    <div
      className={
        cn
          ? cn(
              'relative h-96 w-full bg-black md:h-screen',
              className,
            )
          : `relative h-screen w-full bg-black ${className ?? ''}`
      }
    >
      <PathSVG svgOptions={svgOptions} />
      <div className='relative z-10'>{children}</div>
    </div>
  );
};

const PathSVG = ({ svgOptions }: { svgOptions?: { duration?: number } }) => {
  const prefersReducedMotion = useReducedMotion();
  const reduceComplexity = true;
  const circuits = reduceComplexity ? CIRCUITS.slice(0, 5) : CIRCUITS;
  const nodes = NODES;

  return (
    <motion.svg
      viewBox='0 0 1000 700'
      preserveAspectRatio='xMidYMid slice'
      fill='none'
      xmlns='http://www.w3.org/2000/svg'
      className='absolute inset-0 w-full h-full'
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 1 }}
    >
      <defs>
        <linearGradient id='circuitGradientLight'>
          <stop offset='0%' stopColor='#10b981' />
          <stop offset='50%' stopColor='#3b82f6' />
          <stop offset='100%' stopColor='#8b5cf6' />
        </linearGradient>
        <linearGradient id='circuitGradientDark'>
          <stop offset='0%' stopColor='#00ff41' />
          <stop offset='50%' stopColor='#00d9ff' />
          <stop offset='100%' stopColor='#7c3aed' />
        </linearGradient>
        <filter
          id='circuitPathGlowLight'
          x='-3%'
          y='-5%'
          width='106%'
          height='110%'
        >
          <feGaussianBlur stdDeviation='1.5' result='coloredBlur' />
          <feMerge>
            <feMergeNode in='coloredBlur' />
            <feMergeNode in='SourceGraphic' />
          </feMerge>
        </filter>
        <filter
          id='circuitPathGlowDark'
          x='-4%'
          y='-6%'
          width='108%'
          height='112%'
        >
          <feGaussianBlur stdDeviation='2' result='coloredBlur' />
          <feMerge>
            <feMergeNode in='coloredBlur' />
            <feMergeNode in='SourceGraphic' />
          </feMerge>
        </filter>
        <filter
          id='circuitNodeGlowLight'
          x='-40%'
          y='-40%'
          width='180%'
          height='180%'
        >
          <feGaussianBlur stdDeviation='1.5' result='coloredBlur' />
          <feMerge>
            <feMergeNode in='coloredBlur' />
            <feMergeNode in='SourceGraphic' />
          </feMerge>
        </filter>
        <filter
          id='circuitNodeGlowDark'
          x='-50%'
          y='-50%'
          width='200%'
          height='200%'
        >
          <feGaussianBlur stdDeviation='2' result='coloredBlur' />
          <feMerge>
            <feMergeNode in='coloredBlur' />
            <feMergeNode in='SourceGraphic' />
          </feMerge>
        </filter>
      </defs>

      {circuits.map((path, idx) => (
        <motion.path
          key={`circuit-${idx}`}
          d={path}
          stroke='url(#circuitGradientLight)'
          strokeWidth='3'
          fill='none'
          filter={reduceComplexity ? undefined : 'url(#circuitPathGlowLight)'}
          strokeLinecap='round'
          className={cn(
            'dark:stroke-[url(#circuitGradientDark)]',
            !reduceComplexity && 'dark:filter-[url(#circuitPathGlowDark)]',
          )}
          initial={prefersReducedMotion ? false : { pathLength: 0, opacity: 0 }}
          animate={
            prefersReducedMotion
              ? { pathLength: 1, opacity: 0.65 }
              : {
                  pathLength: [0, 1, 0.8, 1],
                  opacity: [0, 1, 0.4, 1],
                }
          }
          transition={
            prefersReducedMotion
              ? undefined
              : {
                  duration: svgOptions?.duration || 6,
                  repeat: Infinity,
                  delay: idx * 0.5,
                  ease: 'easeInOut',
                }
          }
        />
      ))}

      {nodes.map((node, idx) => (
        <motion.g key={`node-${idx}`}>
          <motion.circle
            cx={node.x}
            cy={node.y}
            r='6'
            fill='url(#circuitGradientLight)'
            filter={reduceComplexity ? undefined : 'url(#circuitNodeGlowLight)'}
            className={cn(
              'dark:fill-[url(#circuitGradientDark)]',
              !reduceComplexity && 'dark:filter-[url(#circuitNodeGlowDark)]',
            )}
            initial={prefersReducedMotion ? false : { scale: 0 }}
            animate={
              prefersReducedMotion ? { scale: 1 } : { scale: [0, 1.3, 1, 1.1, 1] }
            }
            transition={
              prefersReducedMotion
                ? undefined
                : {
                    duration: 2,
                    repeat: Infinity,
                    delay: idx * 0.3,
                    ease: 'easeInOut',
                  }
            }
          />
          {!reduceComplexity && idx < 6 && (
            <motion.circle
              cx={node.x}
              cy={node.y}
              r='12'
              fill='none'
              stroke='url(#circuitGradientLight)'
              strokeWidth='1'
              opacity='0.5'
              className='dark:stroke-[url(#circuitGradientDark)]'
              initial={{ scale: 0 }}
              animate={{ scale: [0, 1.5, 1.2, 1.5] }}
              transition={{
                duration: 3,
                repeat: Infinity,
                delay: idx * 0.3,
                ease: 'easeInOut',
              }}
            />
          )}
        </motion.g>
      ))}
    </motion.svg>
  );
};
