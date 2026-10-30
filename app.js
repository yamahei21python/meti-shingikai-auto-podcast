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
            // Phase 4: the RSS <link> is the council source page, NOT the
            // audio. "Listen Now" must point at the enclosure (MP3) URL;
            // the source page gets its own link.
            const sourceLink = item.querySelector('link')?.textContent || '#';
            const audioUrl = item.querySelector('enclosure')?.getAttribute('url') || sourceLink;

            // Clean up description: remove markdown/HTML and limit length
            const preview = description
                .replace(/<[^>]*>?/gm, '') // Remove HTML tags
                .replace(/[#*`]/g, '')     // Remove common MD chars
                .trim()
                .slice(0, 120) + '...';

            // Phase 4: build the card with DOM APIs and textContent so
            // feed-supplied strings can never inject markup (previously
            // title/preview/link were interpolated into innerHTML).
            const card = document.createElement('div');
            card.className = 'glass-card p-10 flex flex-col group reveal';
            card.style.animationDelay = `${index * 0.1}s`;

            const head = document.createElement('div');
            head.className = 'flex items-center justify-between mb-6';
            const dateSpan = document.createElement('span');
            dateSpan.className = 'text-xs font-bold text-primary tracking-widest uppercase bg-primary/10 px-3 py-1 rounded-full';
            dateSpan.textContent = pubDate;
            const aiSpan = document.createElement('span');
            aiSpan.className = 'text-text-dim text-xs';
            aiSpan.textContent = 'AI Analysis';
            head.append(dateSpan, aiSpan);

            const h3 = document.createElement('h3');
            h3.className = 'text-2xl font-bold mb-4 group-hover:text-primary transition-colors duration-300';
            h3.textContent = title;

            const p = document.createElement('p');
            p.className = 'text-text-muted text-sm leading-relaxed mb-8 line-clamp-3';
            p.textContent = preview;

            const foot = document.createElement('div');
            foot.className = 'mt-auto flex items-center justify-between';
            const links = document.createElement('div');
            links.className = 'flex items-center gap-3';
            const listen = document.createElement('a');
            listen.href = audioUrl;
            listen.target = '_blank';
            listen.className = 'btn btn-outline py-2 px-6 text-xs font-bold uppercase tracking-widest hover:bg-primary hover:text-bg-deep transition-all';
            listen.setAttribute('aria-label', `${title}を聴く`);
            const playIcon = document.createElement('i');
            playIcon.setAttribute('data-lucide', 'play');
            playIcon.className = 'h-3 w-3 fill-current mr-2';
            listen.append(playIcon, document.createTextNode(' Listen Now'));
            links.appendChild(listen);
            if (sourceLink && sourceLink !== audioUrl) {
                const src = document.createElement('a');
                src.href = sourceLink;
                src.target = '_blank';
                src.className = 'text-xs font-bold uppercase tracking-widest text-text-dim hover:text-primary transition-colors';
                src.textContent = '元資料';
                links.appendChild(src);
            }
            const shareWrap = document.createElement('div');
            shareWrap.className = 'flex gap-2';
            const shareBtn = document.createElement('button');
            shareBtn.className = 'p-2 rounded-full hover:bg-white/5 text-text-dim transition-colors';
            shareBtn.title = '共有';
            shareBtn.setAttribute('aria-label', 'エピソードを共有');
            const shareIcon = document.createElement('i');
            shareIcon.setAttribute('data-lucide', 'share-2');
            shareIcon.className = 'h-4 w-4';
            shareBtn.appendChild(shareIcon);
            shareWrap.appendChild(shareBtn);
            foot.append(links, shareWrap);

            card.append(head, h3, p, foot);
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
