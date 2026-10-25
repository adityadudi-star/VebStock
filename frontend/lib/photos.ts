// Unsplash photos (hot-linked from images.unsplash.com, as Unsplash's guidelines expect).
export const PHOTOS = {
  warehouse: { id: "1627309366653-2dedc084cdf1", alt: "Wide warehouse interior with orange racking" },
  staff: { id: "1664382953403-fc1ac77073a0", alt: "Two staff members with a scanner and clipboard in a warehouse aisle" },
  cereal: { id: "1578916171728-46686eac8d58", alt: "Supermarket aisle with cereal boxes" },
  dairy: { id: "1601599561213-832382fd07ba", alt: "Refrigerated dairy display cases" },
  aerial: { id: "1492168732976-2676c584c675", alt: "Aerial view of parked freight trucks" },
  dusk: { id: "1592805144716-feeccccef5ac", alt: "Semi truck on a highway at dusk" },
  racks: { id: "1587293852726-70cdb56c2866", alt: "Boxes on a white metal rack" },
  aisleWorkers: { id: "1586528116022-aeda1613c63d", alt: "Workers walking a warehouse aisle" },
  blueShelves: { id: "1592085198739-ffcad7f36b54", alt: "Blue shelving with boxes" },
  shelves: { id: "1644079446600-219068676743", alt: "Warehouse shelves in a long aisle" },
  grocery: { id: "1604719312566-8912e9227c6a", alt: "Grocery store aisle" },
  gondola: { id: "1515706886582-54c73c5eaf41", alt: "Grocery gondola packed with products" },
  labelled: { id: "1556767576-cf0a4a80e5b8", alt: "Labelled boxes" },
  trucks: { id: "1565793298595-6a879b1d9492", alt: "Parked trucks seen from above" },
  highway: { id: "1501700493788-fa1a4fc9fe62", alt: "Truck on a highway" },
  trailer: { id: "1473445730015-841f29a9490b", alt: "Trailer truck on a road" },
  citrus: { id: "1583258292688-d0213dc5a3a8", alt: "Shelves of citrus fruit" },
} as const;

export type PhotoKey = keyof typeof PHOTOS;

export function photoUrl(key: PhotoKey, w: number): string {
  return `https://images.unsplash.com/photo-${PHOTOS[key].id}?w=${w}&q=70&auto=format&fit=crop`;
}

/** Banner photo for each view. */
export const VIEW_PHOTO: Record<string, PhotoKey> = {
  "/": "warehouse",
  "/overview": "warehouse",
  "/inventory": "shelves",
  "/forecast": "grocery",
  "/plan": "aerial",
  "/tradeoff": "citrus",
  "/simulator": "dusk",
  "/compare": "racks",
  "/alerts": "dairy",
  "/overrides": "staff",
  "/data": "blueShelves",
};
