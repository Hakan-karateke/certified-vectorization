/**
 * Bootstrap Icons arşivinden beyaz zeminli 1000×1000 test PNG'leri ve manifest üretir.
 *
 * Kullanım:
 *   node examples/prepare_icon_dataset.cjs <sharp içeren node_modules> \
 *        examples/icon_dataset/download/bootstrap-icons-1.11.3 examples/icon_dataset
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

async function main() {
  const [modules, source, root] = process.argv.slice(2).map(p => path.resolve(p));
  const sharp = require(path.join(modules, 'sharp'));
  fs.mkdirSync(path.join(root, 'png'), { recursive: true });
  const assets = [];
  const skipped = [];
  const names = fs.readdirSync(source).filter(n => n.endsWith('.svg')).sort();
  for (const name of names) {
    const original = path.join(source, name);
    const id = 'bi_' + path.basename(name, '.svg');
    const png = path.join('png', id + '.png');
    try {
      // 16 birimlik viewBox 4140 dpi'de doğrudan 920 piksele çizilir; büyütme yapılmaz.
      await sharp(original, { density: 4140 })
        .resize(920, 920, { fit: 'contain', background: 'white' })
        .flatten({ background: 'white' })
        .extend({ top: 40, bottom: 40, left: 40, right: 40, background: 'white' })
        .png()
        .toFile(path.join(root, png));
    } catch (error) {
      skipped.push({ name, reason: String(error.message) });
      continue;
    }
    assets.push({
      id,
      source: 'bootstrap-icons',
      name: path.basename(name, '.svg'),
      original_path: path.relative(root, original).split(path.sep).join('/'),
      png_path: png.split(path.sep).join('/'),
      sha256_original: crypto.createHash('sha256').update(fs.readFileSync(original)).digest('hex'),
      sha256_png: crypto
        .createHash('sha256')
        .update(fs.readFileSync(path.join(root, png)))
        .digest('hex'),
      license: 'MIT',
      license_url: 'https://github.com/twbs/icons/blob/main/LICENSE',
      attribution: 'Bootstrap Icons 1.11.3, The Bootstrap Authors',
    });
  }
  const manifest = {
    schema_version: '1.0',
    archive: 'bootstrap-icons-1.11.3.zip',
    archive_url: 'https://github.com/twbs/icons/releases/download/v1.11.3/bootstrap-icons-1.11.3.zip',
    archive_sha256: '100a3d6bd8484d52010b44fa81a2d5b5653f6ddffc20ed6eb346f6517ab64e4f',
    conversion: 'SVG 16x16 viewBox rendered at 4140 dpi -> 920x920 contain, white background, 40 px margin, PNG',
    rasterizer: { sharp: sharp.versions.sharp, librsvg: sharp.versions.rsvg },
    asset_count: assets.length,
    skipped,
    assets,
  };
  fs.writeFileSync(path.join(root, 'manifest.json'), JSON.stringify(manifest, null, 1), 'utf8');
  console.log(assets.length, 'skipped', JSON.stringify(skipped));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
