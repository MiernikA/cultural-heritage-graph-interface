export type FeaturedEntity = {
  uri: string;
  title: string;
  type: string;
  icon: string;
  connections: number;
  recommendationCount: number;
};

export const GRAPH_STATS = {
  entities: 837085,
  relations: 1819354,
  types: 33,
};

export const FEATURED_ENTITIES: FeaturedEntity[] = [
  {
    uri: "http://onto.uj.edu.pl#E21_fRq_UOAKUuQ8",
    title: "Benedykt z Koźmina Wielkopolskiego (Wielkiego Koźmina), syn Jana",
    type: "Person",
    icon: "user",
    connections: 8,
    recommendationCount: 327,
  },
  {
    uri: "http://onto.uj.edu.pl#E21_X2SvdkcwjBwL",
    title: "Sebastian Sierakowski (hrabia)",
    type: "Person",
    icon: "user",
    connections: 250,
    recommendationCount: 371,
  },
  {
    uri: "http://onto.uj.edu.pl#E21_Xtkg8hREqAC8",
    title: "Stanisław Reszka z Buku, syn Stanisława",
    type: "Person",
    icon: "user",
    connections: 30,
    recommendationCount: 470,
  },
  {
    uri: "http://onto.uj.edu.pl#E21_OxaLvL7w840O",
    title: "Jan III Sobieski (król Polski ; 1629-1696)",
    type: "Person",
    icon: "user",
    connections: 223,
    recommendationCount: 348,
  },
  {
    uri: "http://onto.uj.edu.pl#E21_4Jw4m_XU9Bme",
    title: "Maciej Karpiga z Miechowa (Miechowita)",
    type: "Person",
    icon: "user",
    connections: 31,
    recommendationCount: 398,
  },
  {
    uri: "http://onto.uj.edu.pl#E21_XuQT2VUEeUdX",
    title: "Mikołaj Kopernik (Copernicus) z Torunia, syn Mikołaja",
    type: "Person",
    icon: "user",
    connections: 218,
    recommendationCount: 358,
  },
  {
    uri: "http://onto.uj.edu.pl#E21_iLCJNeOu3G68",
    title: "Jakub Górski (młodszy) z Krakowa",
    type: "Person",
    icon: "user",
    connections: 2,
    recommendationCount: 243,
  },
  {
    uri: "http://onto.uj.edu.pl#E21_ncnIluPqZxK6",
    title: "Andrzej z Buku (starszy)",
    type: "Person",
    icon: "user",
    connections: 2,
    recommendationCount: 374,
  },
  {
    uri: "http://onto.uj.edu.pl#E21_oLOqfp9_F7ZK",
    title: "Jan Brożek (Broscius) z Kurzelowa, syn Jakuba",
    type: "Person",
    icon: "user",
    connections: 67,
    recommendationCount: 442,
  },
  {
    uri: "http://onto.uj.edu.pl#E53_rUC51y113BqA",
    title: "Kraków (woj. małopolskie)",
    type: "Place",
    icon: "map-pin",
    connections: 127,
    recommendationCount: 137,
  },
];
