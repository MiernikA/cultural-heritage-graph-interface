import { useEffect, useRef, useState, type ReactNode } from "react";

type Props = {
  as?: "span" | "strong";
  children: ReactNode;
  className?: string;
  title: string;
};

export function OverflowTitle({ as: Component = "span", children, className, title }: Props) {
  const ref = useRef<HTMLElement | null>(null);
  const [isOverflowing, setIsOverflowing] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      setIsOverflowing(false);
      return;
    }

    const updateOverflow = () => {
      setIsOverflowing(element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1);
    };

    updateOverflow();
    const observer = new ResizeObserver(updateOverflow);
    observer.observe(element);
    return () => observer.disconnect();
  }, [children, title]);

  return (
    <Component ref={ref} className={className} title={isOverflowing ? title : undefined}>
      {children}
    </Component>
  );
}
