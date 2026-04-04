document.addEventListener('DOMContentLoaded', async () => {
    const episodeGrid = document.getElementById('episode-grid');
    const lastUpdateEl = document.getElementById('last-update');

    try {
        const response = await fetch('podcast.xml');
        const text = await response.text();
        const parser = new DOMParser();
        const xml = parser.parseFromString(text, 'application/xml');

        const items = xml.querySelectorAll('item');
        const lastBuildDate = xml.querySelector('lastBuildDate')?.textContent;
        
        if (lastBuildDate) {
            lastUpdateEl.textContent = new Date(lastBuildDate).toLocaleDateString('ja-JP');
        }

        // Clear skeletons
        episodeGrid.innerHTML = '';

        items.forEach(item => {
            const title = item.querySelector('title').textContent;
            const pubDate = new Date(item.querySelector('pubDate').textContent).toLocaleDateString('ja-JP');
            const description = item.querySelector('description').textContent;
            const link = item.querySelector('link').textContent;
            
            // Extract a short preview from description (HTML or Markdown)
            // Remove markdown headers and trim
            const preview = description
                .replace(/###\s.*\n/g, '')
                .replace(/\*+/g, '')
                .slice(0, 150) + '...';

            const card = document.createElement('div');
            card.className = 'episode-card group';
            card.innerHTML = `
                <div class="date-tag">${pubDate}</div>
                <h3 class="font-outfit text-xl font-bold mb-3 group-hover:text-sky-300 transition-colors">${title}</h3>
                <p class="text-slate-400 text-sm leading-relaxed line-clamp-3 mb-6">${preview}</p>
                <div class="flex items-center justify-between mt-auto">
                    <a href="${link}" class="inline-flex items-center gap-2 text-xs font-bold text-sky-400 hover:text-sky-300 transition-colors uppercase tracking-widest">
                        <i data-lucide="play" class="h-3 w-3 fill-current"></i> Listen Now
                    </a>
                    <button class="p-2 rounded-full hover:bg-slate-800 text-slate-500 hover:text-slate-300 transition-all outline-none border-none cursor-pointer bg-transparent" title="Share">
                        <i data-lucide="share-2" class="h-4 w-4"></i>
                    </button>
                </div>
            `;
            
            episodeGrid.appendChild(card);
        });

        // Initialize Lucide icons
        lucide.createIcons();

    } catch (error) {
        console.error('Error loading episodes:', error);
        episodeGrid.innerHTML = '<p class="text-red-400">Failed to load episodes. Please check your network connection.</p>';
    }
});
