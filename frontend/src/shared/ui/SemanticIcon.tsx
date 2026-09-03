import {
  Badge,
  BookOpen,
  BriefcaseBusiness,
  Building,
  Building2,
  CircleDot,
  Clock,
  GraduationCap,
  Landmark,
  Languages,
  MapPin,
  Tags,
  User,
} from "lucide-react";

type Props = {
  name: string;
  size?: number;
};

const icons = {
  badge: Badge,
  "book-open": BookOpen,
  "briefcase-business": BriefcaseBusiness,
  building: Building,
  "building-2": Building2,
  "circle-dot": CircleDot,
  clock: Clock,
  "graduation-cap": GraduationCap,
  landmark: Landmark,
  languages: Languages,
  tag: Tags,
  tags: Tags,
  user: User,
  "map-pin": MapPin,
};

export function SemanticIcon({ name, size = 18 }: Props) {
  const Icon = icons[name as keyof typeof icons] ?? CircleDot;
  return <Icon size={size} aria-hidden="true" />;
}
