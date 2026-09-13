// Raster variants of the same vector used by Next.js for the browser icon.
// Run from any directory: node web/scripts/generate-icons.mjs
import { readFile, writeFile } from "node:fs/promises";
import sharp from "sharp";
import { fileURLToPath } from "node:url";

const app = new URL("../app/", import.meta.url);
const svg = await readFile(new URL("icon.svg", app));
await sharp(svg).resize(180, 180).png().toFile(fileURLToPath(new URL("apple-icon.png", app)));

// ICO supports PNG-encoded entries; include common browser-tab resolutions.
const sizes = [16, 32, 48];
const images = await Promise.all(sizes.map(size => sharp(svg).resize(size, size).png().toBuffer()));
const header = Buffer.alloc(6 + 16 * images.length);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(images.length, 4);
let offset = header.length;
images.forEach((png, index) => {
  const entry = 6 + index * 16;
  header[entry] = header[entry + 1] = sizes[index];
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(png.length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += png.length;
});
await writeFile(new URL("favicon.ico", app), Buffer.concat([header, ...images]));
console.log("Generated favicon.ico (16/32/48px) and apple-icon.png (180px).");
