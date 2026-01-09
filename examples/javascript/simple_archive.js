/**
 * Simple archive example - Archive a single URL with HTBase.
 *
 * Usage:
 *   node simple_archive.js
 *
 * Requirements:
 *   npm install node-fetch
 */

const fetch = require('node-fetch');

/**
 * Archive a single URL using HTBase.
 *
 * @param {string} url - The URL to archive
 * @param {string} itemId - Unique identifier for this archive
 * @param {string} archiver - Archiver to use (default: readability)
 * @param {string} baseUrl - HTBase API base URL
 * @returns {Promise<object>} Archive result
 */
async function archiveUrl(
  url,
  itemId,
  archiver = 'readability',
  baseUrl = 'http://localhost:8000'
) {
  const endpoint = `${baseUrl}/api/save/${archiver}`;

  const payload = {
    url: url,
    id: itemId
  };

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload),
    timeout: 300000 // 5 minutes
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }

  return response.json();
}

/**
 * Main function - example usage.
 */
async function main() {
  // Configuration
  const URL_TO_ARCHIVE = 'https://example.com';
  const ITEM_ID = 'example-article-2026-01-09';
  const ARCHIVER = 'readability';

  console.log(`Archiving: ${URL_TO_ARCHIVE}`);
  console.log(`Item ID: ${ITEM_ID}`);
  console.log(`Archiver: ${ARCHIVER}`);
  console.log('-'.repeat(50));

  try {
    // Archive the URL
    const result = await archiveUrl(URL_TO_ARCHIVE, ITEM_ID, ARCHIVER);

    // Check result
    if (result.ok && result.exit_code === 0) {
      console.log('✅ Archive successful!');
      console.log(`Saved to: ${result.saved_path}`);
      console.log(`Database row ID: ${result.db_rowid}`);
    } else {
      console.log('❌ Archive failed!');
      console.log(`Exit code: ${result.exit_code}`);
      console.log('Details:', result);
    }
  } catch (error) {
    console.error('❌ Error:', error.message);
  }
}

// Run if executed directly
if (require.main === module) {
  main().catch(console.error);
}

// Export for use as module
module.exports = { archiveUrl };
