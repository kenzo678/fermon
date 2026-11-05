import type { Tank } from "../../../shared/api";
import { TankCard } from "./TankCard";

interface TankGridProps {
  tanks: Tank[];
}

export function TankGrid({ tanks }: TankGridProps) {
  return (
    <ul
      aria-label="Tanks"
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
    >
      {tanks.map((tank) => (
        <li key={tank.id}>
          <TankCard tank={tank} />
        </li>
      ))}
    </ul>
  );
}
