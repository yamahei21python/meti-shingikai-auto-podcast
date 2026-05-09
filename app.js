/**
 * Energy Audio - Dynamic Episode Loader
 * Fetches and parses the podcast.xml RSS feed to display latest episodes.
 */

document.addEventListener('DOMContentLoaded', async () => {
    const episodeGrid = document.getElementById('episode-grid');
    const lastUpdateEl = document.getElementById('last-update');

    // Function to create a skeleton pulse card
    const createSkeleton = () => `
        <div class="glass-card p-8 animate-pulse">
            <div class="h-6 w-1/4 bg-white/5 rounded-full mb-6"></div>
            <div class="h-8 w-3/4 bg-white/5 rounded-lg mb-4"></div>
            <div class="space-y-2">
                <div class="h-4 w-full bg-white/5 rounded"></div>
                <div class="h-4 w-5/6 bg-white/5 rounded"></div>
            </div>
        </div>
    `;

    // Show skeletons initially
    episodeGrid.innerHTML = createSkeleton() + createSkeleton();

    try {
        const response = await fetch('https://energy-audio.vercel.app/feed');
        if (!response.ok) throw new Error('Failed to fetch podcast feed');
        
        const text = await response.text();
        const parser = new DOMParser();
        const xml = parser.parseFromString(text, 'application/xml');

        // Check for parsing errors
        const parseError = xml.querySelector('parsererror');
        if (parseError) throw new Error('XML parsing error');

        const items = Array.from(xml.querySelectorAll('item')).slice(0, 6); // Get last 6 episodes
        const lastBuildDate = xml.querySelector('lastBuildDate')?.textContent || 
                             xml.querySelector('pubDate')?.textContent;
        
        if (lastBuildDate && lastUpdateEl) {
            const date = new Date(lastBuildDate);
            lastUpdateEl.textContent = !isNaN(date) ? date.toLocaleString('ja-JP') : '--';
        }

        // Clear skeletons
        episodeGrid.innerHTML = '';

        if (items.length === 0) {
            episodeGrid.innerHTML = '<p class="text-text-muted text-center col-span-full py-12">配信中のエピソードはまだありません。</p>';
            return;
        }

        items.forEach((item, index) => {
            const title = item.querySelector('title')?.textContent || 'Untitled Episode';
            const rawDate = item.querySelector('pubDate')?.textContent;
            const pubDate = rawDate && !isNaN(new Date(rawDate)) 
                ? new Date(rawDate).toLocaleDateString('ja-JP') 
                : '不明な日付';
            
            const description = item.querySelector('description')?.textContent || '';
            const link = item.querySelector('link')?.textContent || '#';
            
            // Clean up description: remove markdown/HTML and limit length
            const preview = description
                .replace(/<[^>]*>?/gm, '') // Remove HTML tags
                .replace(/[#*`]/g, '')     // Remove common MD chars
                .trim()
                .slice(0, 120) + '...';

            const card = document.createElement('div');
            card.className = 'glass-card p-10 flex flex-col group reveal';
            card.style.animationDelay = `${index * 0.1}s`;
            
            card.innerHTML = `
                <div class="flex items-center justify-between mb-6">
                    <span class="text-xs font-bold text-primary tracking-widest uppercase bg-primary/10 px-3 py-1 rounded-full">
                        ${pubDate}
                    </span>
                    <span class="text-text-dim text-xs">AI Analysis</span>
                </div>
                <h3 class="text-2xl font-bold mb-4 group-hover:text-primary transition-colors duration-300">
                    ${title}
                </h3>
                <p class="text-text-muted text-sm leading-relaxed mb-8 line-clamp-3">
                    ${preview}
                </p>
                <div class="mt-auto flex items-center justify-between">
                    <a href="${link}" target="_blank" class="btn btn-outline py-2 px-6 text-xs font-bold uppercase tracking-widest hover:bg-primary hover:text-bg-deep transition-all" aria-label="${title}を聴く">
                        <i data-lucide="play" class="h-3 w-3 fill-current mr-2"></i> Listen Now
                    </a>
                    <div class="flex gap-2">
                        <button class="p-2 rounded-full hover:bg-white/5 text-text-dim transition-colors" title="共有" aria-label="エピソードを共有">
                            <i data-lucide="share-2" class="h-4 w-4"></i>
                        </button>
                    </div>
                </div>
            `;
            
            episodeGrid.appendChild(card);
        });

        // Re-initialize Lucide icons for dynamic content
        if (window.lucide) {
            window.lucide.createIcons();
        }

    } catch (error) {
        console.error('Error loading episodes:', error);
        episodeGrid.innerHTML = `
            <div class="col-span-full text-center py-12 glass-card border-red-500/20 bg-red-500/5">
                <i data-lucide="alert-triangle" class="h-12 w-12 text-red-400 mb-4 mx-auto"></i>
                <p class="text-red-400 font-bold mb-2">エピソードの読み込みに失敗しました</p>
                <p class="text-text-dim text-sm">公式プラットフォーム（Spotify/Apple）で直接ご確認ください。</p>
            </div>
        `;
        if (window.lucide) window.lucide.createIcons();
    }
});
