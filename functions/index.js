const functions = require('firebase-functions');
const admin = require('firebase-admin');
const axios = require('axios');

admin.initializeApp();
const db = admin.firestore();

/**
 * Triggered when user saves an article to their personal collection.
 * Checks if shared article exists; if not, creates it and triggers archival.
 */
exports.onUserArticleSave = functions.firestore
  .document('users/{userId}/articles/{itemId}')
  .onCreate(async (snap, context) => {
    const userId = context.params.userId;
    const itemId = context.params.itemId;
    const userArticle = snap.data();

    console.log(`User ${userId} saved article ${itemId}`);

    // Validate required fields
    if (!userArticle.url) {
      console.error(`Missing URL for article ${itemId}`);
      await snap.ref.update({
        error: 'Missing URL',
        error_at: admin.firestore.FieldValue.serverTimestamp()
      });
      return null;
    }

    try {
      // Check if article with this URL already exists (query by URL, not itemId)
      const existingArticlesQuery = await db.collection('articles')
        .where('url', '==', userArticle.url)
        .limit(1)
        .get();

      if (!existingArticlesQuery.empty) {
        // Article already archived - link to existing one
        const existingArticle = existingArticlesQuery.docs[0];
        const existingItemId = existingArticle.id;
        const existingData = existingArticle.data();

        console.log(`Article with URL already exists as ${existingItemId}, linking user save`);

        await snap.ref.update({
          // article_ref: existingArticle.ref.path,
          resolvedId: existingItemId,  // Track which shared article this links to
          // linked_at: admin.firestore.FieldValue.serverTimestamp()
        });

        // Increment save count on existing shared article
        await existingArticle.ref.update({
          'stats.total_saves': admin.firestore.FieldValue.increment(1),
          'stats.last_saved_at': admin.firestore.FieldValue.serverTimestamp()
        });

        return null;
      }

      // Article doesn't exist - create shared article and trigger archival
      console.log(`Creating new shared article ${itemId} and triggering archival`);

      const sharedArticleRef = db.collection('articles').doc(itemId);

      // Extract domain from URL
      let domain = '';
      try {
        const urlObj = new URL(userArticle.url);
        domain = urlObj.hostname.replace('www.', '');
      } catch (e) {
        console.error(`Failed to parse URL for domain: ${userArticle.url}`);
      }

      // Prefill pocket data from user save (if available)
      const pocketData = userArticle.pocket_data || userArticle.pocket || {};

      // Create shared article document
      await sharedArticleRef.set({
        item_id: itemId,
        url: userArticle.url,
        domain: domain,
        created_at: admin.firestore.FieldValue.serverTimestamp(),
        // created_by_user: userId,
        status: 'pending',
        archives: {},
        metadata: {},
        pocket: pocketData,
        stats: {
          total_saves: 1,
          total_views: 0
        }
      });

      // Call HTBase API to start archival
      const htbaseUrl = process.env.HTBASE_URL || 'http://localhost:8080';
      const response = await axios.post(`${htbaseUrl}/firebase/archive`, {
        item_id: itemId,
        url: userArticle.url,
        archiver: userArticle.archiver || 'all'
      }, {
        headers: {
          'Content-Type': 'application/json',
        },
        timeout: 10000
      });

      console.log(`HTBase archival started for ${itemId}:`, response.data);

      // Link user save to shared article
      await snap.ref.update({
        // article_ref: sharedArticleRef.path,
        resolvedId: itemId,  // Same as itemId since we just created it
        // linked_at: admin.firestore.FieldValue.serverTimestamp(),
        archival_triggered: true
      });

      // Update shared article status to processing
      await sharedArticleRef.update({
        status: 'processing',
        processing_started_at: admin.firestore.FieldValue.serverTimestamp()
      });

      return null;

    } catch (error) {
      console.error(`Error processing article save ${itemId}:`, error);

      // Update shared article if it was created
      const sharedArticleRef = db.collection('articles').doc(itemId);
      const sharedArticleDoc = await sharedArticleRef.get();

      if (sharedArticleDoc.exists && sharedArticleDoc.data().status === 'pending') {
        await sharedArticleRef.update({
          status: 'failed',
          error: error.message,
          failed_at: admin.firestore.FieldValue.serverTimestamp()
        });
      }

      // Mark user save with error
      await snap.ref.update({
        error: error.message,
        error_at: admin.firestore.FieldValue.serverTimestamp()
      });

      return null;
    }
  });

/**
 * Triggered when article's archive status changes.
 * Increments stats when archival completes successfully.
 */
exports.onArchiveStatusChange = functions.firestore
  .document('articles/{itemId}')
  .onUpdate(async (change, context) => {
    const before = change.before.data();
    const after = change.after.data();
    const itemId = context.params.itemId;

    // Check if status changed from pending/processing to completed
    const statusChanged = before.status !== after.status;
    const isCompleted = after.status === 'completed';

    if (statusChanged && isCompleted) {
      console.log(`Article ${itemId} archival completed`);

      // Sync to PostgreSQL if enabled
      const syncToPg = process.env.SYNC_TO_POSTGRES === 'true';
      if (syncToPg) {
        try {
          const htbaseUrl = process.env.HTBASE_URL;
          await axios.post(`${htbaseUrl}/sync/firestore-to-postgres`, {
            item_id: itemId
          });
          console.log(`Synced ${itemId} to PostgreSQL`);
        } catch (error) {
          console.error(`Failed to sync ${itemId} to PostgreSQL:`, error.message);
        }
      }

      // Update stats
      await change.after.ref.update({
        'stats.last_updated': admin.firestore.FieldValue.serverTimestamp()
      });
    }

    return null;
  });
