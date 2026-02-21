import fs from 'fs';
import path from 'path';

const DB_PATH = path.join(process.cwd(), 'data', 'hyopps.db');

if (fs.existsSync(DB_PATH)) {
  fs.unlinkSync(DB_PATH);
  console.log('Database reset');
}
