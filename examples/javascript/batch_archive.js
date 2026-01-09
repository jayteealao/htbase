/**
 * Batch archive example - Archive multiple URLs efficiently.
 *
 * Usage:
 *   node batch_archive.js
 *
 * Requirements:
 *   npm install node-fetch
 */

const fetch = require('node-fetch');

/**
 * HTBase API client.
 */
class HTBaseClient {
  /**
   * Create HTBase client.
   *
   * @param {string} baseUrl - HTBase API base URL
   */
  constructor(baseUrl = 'http://localhost:8000') {
    this.baseUrl = baseUrl;
  }

  /**
   * Submit batch archive request.
   *
   * @param {Array<{url: string, id: string}>} items - Items to archive
   * @param {string} archiver - Archiver to use
   * @returns {Promise<string>} Task ID
   */
  async batchArchive(items, archiver = 'readability') {
    const endpoint = `${this.baseUrl}/api/batch/${archiver}`;

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ items }),
      timeout: 30000
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    const result = await response.json();
    return result.task_id;
  }

  /**
   * Get status of a batch task.
   *
   * @param {string} taskId - Task ID from batchArchive()
   * @returns {Promise<object>} Task status
   */
  async getTaskStatus(taskId) {
    const endpoint = `${this.baseUrl}/api/tasks/${taskId}`;

    const response = await fetch(endpoint, {
      timeout: 10000
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`HTTP ${response.status}: ${text}`);
    }

    return response.json();
  }

  /**
   * Wait for batch task to complete.
   *
   * @param {string} taskId - Task ID to wait for
   * @param {number} pollInterval - Seconds between status checks
   * @param {number} maxWait - Maximum seconds to wait
   * @returns {Promise<object>} Final task status
   */
  async waitForCompletion(taskId, pollInterval = 5, maxWait = 600) {
    const start = Date.now();

    while (Date.now() - start < maxWait * 1000) {
      const status = await this.getTaskStatus(taskId);

      // Check if completed
      if (status.status === 'success' || status.status === 'failed') {
        return status;
      }

      // Wait before next poll
      await new Promise(resolve => setTimeout(resolve, pollInterval * 1000));
    }

    throw new Error(`Task ${taskId} did not complete in ${maxWait}s`);
  }
}

/**
 * Main function - example usage.
 */
async function main() {
  // Initialize client
  const client = new HTBaseClient();

  // URLs to archive
  const urlsToArchive = [
    'https://example.com/article-1',
    'https://example.com/article-2',
    'https://example.com/article-3',
    'https://example.com/article-4',
    'https://example.com/article-5'
  ];

  // Prepare batch items
  const items = urlsToArchive.map((url, i) => ({
    url: url,
    id: `article-${i + 1}`
  }));

  console.log(`Batch archiving ${items.length} URLs...`);
  console.log('-'.repeat(50));

  try {
    // Submit batch request
    const taskId = await client.batchArchive(items, 'readability');
    console.log(`✅ Batch task created: ${taskId}`);

    // Wait for completion
    console.log('Waiting for completion...');
    const result = await client.waitForCompletion(taskId, 5);

    // Print results
    console.log('-'.repeat(50));
    console.log(`Batch status: ${result.status}`);
    console.log(`Total items: ${result.items.length}`);

    // Count successes and failures
    const successes = result.items.filter(item => item.status === 'success');
    const failures = result.items.filter(item => item.status === 'failed');

    console.log(`✅ Successful: ${successes.length}`);
    console.log(`❌ Failed: ${failures.length}`);

    // Print details
    if (successes.length > 0) {
      console.log('\nSuccessful archives:');
      successes.forEach(item => {
        console.log(`  - ${item.id}: ${item.saved_path}`);
      });
    }

    if (failures.length > 0) {
      console.log('\nFailed archives:');
      failures.forEach(item => {
        console.log(`  - ${item.id}: exit_code=${item.exit_code || 'unknown'}`);
      });
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
module.exports = { HTBaseClient };
