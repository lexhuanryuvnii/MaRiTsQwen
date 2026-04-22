// Все JSdoc и комментарии должны быть переведены на русский язык!
class MetricsDashboard extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this.charts = new Map();
        this.eventSource = null;
        this.allAvailableMetrics = [];
        this.selectedMetrics = new Set();
        this.isInitialized = false;
        this.pendingChanges = false; // Флаг наличия неподтвержденных изменений
        
        this._debounceTime = 3000;
        this._connectDebounceTimer = null;
        this._connectToStreamImpl = this._connectToStreamImpl.bind(this);        
        // Палитра для графиков
        this.colors = ['#38bdf8', '#22c55e', '#f97316', '#a855f7', '#ef4444', '#eab308'];
        
        // Хранилище всех точек для каждой метрики (для накопления данных)
        this.metricsDataStore = new Map();
        
        // Словарь локализации и конфигурации метрик
        this.metricConfig = {
            'cpu.core0_usage_percent': {
                title: 'CPU Ядро 0',
                unit: '%',
                min: 0,
                max: 100,
                step: 10
            },
            'cpu.core1_usage_percent': {
                title: 'CPU Ядро 1',
                unit: '%',
                min: 0,
                max: 100,
                step: 10
            },
            'cpu.core2_usage_percent': {
                title: 'CPU Ядро 2',
                unit: '%',
                min: 0,
                max: 100,
                step: 10
            },
            'cpu.core3_usage_percent': {
                title: 'CPU Ядро 3',
                unit: '%',
                min: 0,
                max: 100,
                step: 10
            },
            'cpu.freq.current_mhz': {
                title: 'Частота CPU',
                unit: 'МГц',
                min: 0,
                max: 5000,
                step: 500
            },
            'cpu.usage_percent': {
                title: 'Загрузка CPU (общая)',
                unit: '%',
                min: 0,
                max: 100,
                step: 10
            },
            'memory.percent_usage': {
                title: 'Использование памяти',
                unit: '%',
                min: 0,
                max: 100,
                step: 10
            },
            'memory.used': {
                title: 'Использовано памяти',
                unit: 'Б',
                min: 0,
                max: null,
                step: null,
                formatBytes: true
            }
        };
    }

    static get observedAttributes() {
        return ['server-url', 'interval', 'minutes'];
    }

    attributeChangedCallback(name, oldVal, newVal) {
        if (oldVal !== newVal && this.isInitialized && name !== 'interval' && name !== 'minutes') {
            this.connectToStream();
        }
    }

    connectedCallback() {
        this.render();
        this.setupEventListeners();
        this.initDashboard();
        this.isInitialized = true;
    }

    setupEventListeners() {
        const intervalInput = this.shadowRoot.querySelector('#interval-input');
        const minutesInput = this.shadowRoot.querySelector('#minutes-input');
        const applyBtn = this.shadowRoot.querySelector('#apply-params-btn');

        // Отслеживание изменений в полях
        [intervalInput, minutesInput].forEach(input => {
            input.addEventListener('input', () => {
                this.pendingChanges = true;
                this.updateApplyButtonState();
            });
            
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.applyParameters();
                }
            });
        });

        // Кнопка применения
        if (applyBtn) {
            applyBtn.addEventListener('click', () => {
                this.applyParameters();
            });
        }
    }

    updateApplyButtonState() {
        const btn = this.shadowRoot.querySelector('#apply-params-btn');
        if (!btn) return;

        if (this.pendingChanges) {
            btn.classList.add('pending');
            btn.innerHTML = `${this.getIcon('refresh')} Применить`;
            btn.title = 'Есть неподтвержденные изменения';
        } else {
            btn.classList.remove('pending');
            btn.innerHTML = `${this.getIcon('check')} Применено`;
            btn.title = 'Параметры применены';
        }
    }

    applyParameters() {
        const intervalInput = this.shadowRoot.querySelector('#interval-input');
        const minutesInput = this.shadowRoot.querySelector('#minutes-input');
        
        const newInterval = parseInt(intervalInput.value) || 20;
        const newMinutes = parseInt(minutesInput.value) || 30;

        // Валидация
        if (newInterval < 1 || newInterval > 300) {
            alert('Интервал должен быть от 1 до 300 секунд');
            return;
        }
        
        if (newMinutes < 1 || newMinutes > 1440) {
            alert('Глубина должна быть от 1 до 1440 минут (24 часа)');
            return;
        }

        // Обновляем атрибуты
        this.setAttribute('interval', newInterval);
        this.setAttribute('minutes', newMinutes);

        // Сбрасываем флаг изменений
        this.pendingChanges = false;
        this.updateApplyButtonState();

        // Переподключаемся с новыми параметрами
        this.flushConnectToStream();
        
        // Обновляем все графики с новым временным окном
        this.updateChartsTimeRange();
        

        // Визуальная обратная связь
        this.showNotification(`Параметры обновлены: ${newInterval}с / ${newMinutes}мин`);

    }

    showNotification(message) {
        // Создаем временное уведомление
        const notification = document.createElement('div');
        notification.className = 'notification';
        notification.textContent = message;
        
        const container = this.shadowRoot.querySelector('.header');
        container.appendChild(notification);
        
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);
        
        setTimeout(() => {
            notification.classList.remove('show');
            setTimeout(() => notification.remove(), 300);
        }, 2000);
    }

    updateChartsTimeRange() {
        const now = Date.now();
        const cutoff = now - (this.getAttribute('minutes') || 30) * 60 * 1000;

        // Очищаем старые точки в хранилище для всех метрик
        for (const [name, data] of this.metricsDataStore.entries()) {
            while (data.length > 0 && data[0].x < cutoff) {
                data.shift();
            }
        }

        // Обновляем графики с новыми границами и отфильтрованными данными
        for (const chart of this.charts.values()) {
            const metricName = chart.data.datasets[0].label;
            const existingData = this.metricsDataStore.get(metricName) || [];
            chart.data.datasets[0].data = existingData;
            chart.options.scales.x.min = cutoff;
            chart.options.scales.x.max = now;
            chart.update('none');
        }
    }

    getMetricInfo(metricName) {
        return this.metricConfig[metricName] || {
            title: metricName,
            unit: '',
            min: undefined,
            max: undefined,
            step: undefined
        };
    }

    formatValue(value, unit, formatBytes = false) {
        if (formatBytes) {
            return this.formatBytes(value);
        }
        return `${value.toFixed(1)} ${unit}`;
    }

    formatBytes(bytes) {
        if (bytes === 0) return '0 Б';
        const k = 1024;
        const sizes = ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async initDashboard() {
        const serverUrl = this.getAttribute('server-url') || '';
        this.setStatus('connecting', 'Получение списка метрик...');
        
        // Устанавливаем начальные значения в поля ввода
        const intervalInput = this.shadowRoot.querySelector('#interval-input');
        const minutesInput = this.shadowRoot.querySelector('#minutes-input');
        
        if (intervalInput) intervalInput.value = this.getAttribute('interval') || 20;
        if (minutesInput) minutesInput.value = this.getAttribute('minutes') || 30;
        
        try {
            const response = await fetch(`${serverUrl}/metrics/names`);
            if (!response.ok) throw new Error('Сервер недоступен');
            const data = await response.json();

            this.allAvailableMetrics = data.metrics;
            this.allAvailableMetrics.slice(0, 3).forEach(m => this.selectedMetrics.add(m));
            
            // Очищаем хранилище данных при инициализации
            this.metricsDataStore.clear();
            
            this.renderMetricToggles();
            this.rebuildCharts();
            this.connectToStream();
            // this.fetchAnalysis();
            this.setStatus('online', 'Подключено. Идет обновление метрик...');
            this.updateApplyButtonState();
        } catch (err) {
            this.setStatus('error', err.message);
        }
    }

    setStatus(type, text) {
        const statusEl = this.shadowRoot.querySelector('#status-indicator');
        const statusText = this.shadowRoot.querySelector('#status-text');
        if (!statusEl) return;
        
        statusEl.className = `status-dot ${type}`;
        statusText.textContent = text;
    }

    renderMetricToggles() {
        const container = this.shadowRoot.querySelector('.metrics-selector');
        container.innerHTML = this.allAvailableMetrics.map(m => {
            const info = this.getMetricInfo(m);
            return `
            <div class="metric-chip ${this.selectedMetrics.has(m) ? 'active' : ''}" data-metric="${m}">
                ${this.selectedMetrics.has(m) ? this.getIcon('check') : this.getIcon('plus')}
                ${info.title}
            </div>
        `}).join('');

        container.querySelectorAll('.metric-chip').forEach(chip => {
            chip.onclick = () => {
                const m = chip.dataset.metric;
                if (this.selectedMetrics.has(m)) {
                    this.selectedMetrics.delete(m);
                } else {
                    this.selectedMetrics.add(m);
                }
                this.renderMetricToggles();
                this.rebuildCharts();
                this.connectToStream();
            };
        });
    }

    rebuildCharts() {
        const container = this.shadowRoot.querySelector('.charts-grid');
        for (const [name, chart] of this.charts) {
            if (!this.selectedMetrics.has(name)) {
                chart.destroy();
                this.charts.delete(name);
                // Очищаем данные из хранилища для удаленной метрики
                this.metricsDataStore.delete(name);
                container.querySelector(`[data-wrapper="${name}"]`)?.remove();
            }
        }

        Array.from(this.selectedMetrics).forEach((metric, index) => {
            if (!this.charts.has(metric)) {
                const wrapper = document.createElement('div');
                wrapper.className = 'chart-card';
                wrapper.dataset.wrapper = metric;
                const color = this.colors[index % this.colors.length];        
                const info = this.getMetricInfo(metric);
                
                wrapper.innerHTML = `
                    <div class="chart-header">
                        <span class="chart-icon" style="color: ${color}">${this.getIcon('chart')}</span>
                        <div class="chart-title">${info.title}</div>
                        ${info.unit ? `<div class="chart-unit">${info.unit}</div>` : ''}
                    </div>
                    <div class="canvas-container">
                        <canvas id="chart-${metric}"></canvas>
                    </div>
                `;
                container.appendChild(wrapper);
                const ctx = wrapper.querySelector('canvas').getContext('2d');
                this.charts.set(metric, this.createChart(ctx, metric, color, info));
            } else {
                // Если график уже существует, обновляем его данные из хранилища
                const existingData = this.metricsDataStore.get(metric) || [];
                const chart = this.charts.get(metric);
                chart.data.datasets[0].data = existingData;
                chart.update('none');
            }
        });
    }

    async connectToStream() {
        clearTimeout(this._connectDebounceTimer);
        this._connectDebounceTimer = setTimeout(() => {
            this._connectToStreamImpl();
            this.fetchAnalysis();
        }, this._debounceTime);
    }

    async flushConnectToStream() {
        clearTimeout(this._connectDebounceTimer);
        this._connectToStreamImpl();
        this.fetchAnalysis();
    }

    _connectToStreamImpl() {
        this.setStatus('connecting', 'Обновление метрик...');
        if (this.eventSource) this.eventSource.close();
        if (this.selectedMetrics.size === 0) return;

        const interval = Math.max(5, parseInt(this.getAttribute('interval') || 20));
        const minutes = Math.max(5, parseInt(this.getAttribute('minutes') || 30));

        if (interval < 5 || minutes < 5) {
            this.setStatus('connecting', 'Неправильные параметры. Интервал и минуты должны быть не меньше 5.');
            return;
        }

        const params = new URLSearchParams({
            interval: interval,
            minutes: minutes,
            metrics: Array.from(this.selectedMetrics).join(','),
            t: Date.now()
        });

        const url = `${this.getAttribute('server-url') || ''}/metrics/stream?${params}`;
        // console.log('Устанавливаем соединение:', url);
        
        this.eventSource = new EventSource(url);

        this.eventSource.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (data.metrics) this.updateCharts(data.metrics);
                this.setStatus('online', `Обновлено: ${new Date().toLocaleTimeString()} (${interval}с/${minutes}мин)`);
            } catch (err) { console.error(err); }
        };

        let retryTime = 5000;
        this.eventSource.onerror = () => {
            this.setStatus('connecting', `Соединение потеряно. Переподключение через ${retryTime}ms`);
            setTimeout(() => {
                this._connectToStreamImpl();
                retryTime = Math.min(retryTime * 2, 60000);
                if (retryTime == 60000) {
                    this.setStatus('offline', 'Соединение потеряно. Попробуйте подключиться позже');
                    return               
                }
            }, retryTime);
        };
    }

    createChart(ctx, label, color, metricInfo) {
        return new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [{
                    label: label,
                    data: [],
                    borderColor: color,
                    backgroundColor: color + '1A',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 400 },
                interaction: {
                    intersect: false,
                    mode: 'index'
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const value = context.parsed.y;
                                return this.formatValue(value, metricInfo.unit, metricInfo.formatBytes);
                            }
                        }
                    }
                },
                scales: {
                    x: { 
                        type: 'time',
                        time: {
                            displayFormats: {
                                minute: 'HH:mm',
                                second: 'HH:mm:ss'
                            }
                        },
                        grid: { display: false, color: '#334155' }, 
                        ticks: { 
                            color: '#94a3b8',
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 6
                        }
                    },
                    y: { 
                        grid: { color: '#334155' }, 
                        ticks: { 
                            color: '#94a3b8',
                            callback: (value) => {
                                if (metricInfo.formatBytes) {
                                    return this.formatBytes(value);
                                }
                                return value + (metricInfo.unit ? ' ' + metricInfo.unit : '');
                            }
                        },
                        min: metricInfo.min,
                        max: metricInfo.max,
                        stepSize: metricInfo.step
                    }
                }
            }
        });
    }

    async fetchAnalysis() {
        // Если ничего не выбрано → очищаем таблицу
        if (this.selectedMetrics.size === 0) {
            console.log(`[fetchAnalysis] No metrics selected, clearing table ${this.selectedMetrics}`);
            this.renderStatsTable(null);
            return;
        }
        
        const serverUrl = this.getAttribute('server-url') || '';
        const params = new URLSearchParams({
            metrics: Array.from(this.selectedMetrics).join(','),
            minutes: this.getAttribute('minutes') || 30
        });

        try {
            const response = await fetch(`${serverUrl}/metrics/analysis?${params}`);
            if (!response.ok) {
                console.warn(`[fetchAnalysis] Failed to fetch analysis, status: ${response.status}`);
                return;
            }
            
            const data = await response.json();
            console.log('[fetchAnalysis] Fetched analysis:', data);
            // Безопасное извлечение: если stats нет или null → пустой объект
            this.renderStatsTable(data?.stats ?? {});
        } catch (err) {
            console.error('[fetchAnalysis] Failed to fetch analysis:', err);
            this.renderStatsTable(null);
        }
    }

    formatStatValue(value, metricInfo) {
        if (value === undefined || value === null) return '—';

        // 1. Проверка на байты (память)
        if (metricInfo.formatBytes) {
            return this.formatBytes(value);
        }

        // 2. Если есть единица измерения (%, МГц)
        if (metricInfo.unit) {
            // Для обычных значений округляем до 2 знаков
            // Если это тренд (изменение в секунду), логично было бы добавить "/с", 
            // но пока оставим просто число с единицей, чтобы не усложнять интерфейс
            return `${value.toFixed(2)} ${metricInfo.unit}`;
        }

        // 3. Неизвестная метрика — округляем, но без единиц
        return value.toFixed(2);
    }

    renderStatsTable(stats) {
        let container = this.shadowRoot.querySelector('.stats-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'stats-container';
            const grid = this.shadowRoot.querySelector('.metrics-selector');
            grid.after(container);
        }

        if (!stats || typeof stats !== 'object' || Object.keys(stats).length === 0) {
            container.innerHTML = `<div class="stats-empty">Выберите метрики для отображения аналитики</div>`;
            return;
        }

        const rows = Object.entries(stats).map(([metricName, stat]) => {
            // Получаем конфиг конкретной метрики
            const info = this.getMetricInfo(metricName);
            
            // Определяем иконку и цвет для тренда
            const trendIcon = stat.is_increasing ? '📈' : '📉';
            const trendClass = stat.is_increasing ? 'text-red' : 'text-green';
            
            // Форматируем значения через наш новый хелпер
            const fmtMean = this.formatStatValue(stat.mean, info);
            const fmtMin = this.formatStatValue(stat.min_val, info);
            const fmtMax = this.formatStatValue(stat.max_val, info);
            const fmtLast = this.formatStatValue(stat.last_value, info);
            
            // Тренд тоже форматируем, но добавим пометку скорости, если есть единица
            let fmtTrend = this.formatStatValue(Math.abs(stat.trend), info);
            // Для тренда логично добавить "/с" (в секунду), если это не байты (там форматБайтс сам разберется)
            if (!info.formatBytes && info.unit) {
                fmtTrend += '/с'; 
            }
            const trendSign = stat.trend > 0 ? '+' : '';

            return `
            <div class="stat-row">
                <div class="stat-name">${info.title}</div>
                <div class="stat-val">
                    <span>Среднее:</span> <b>${fmtMean}</b>
                </div>
                <div class="stat-val">
                    <span>Мин/Макс:</span> <span>${fmtMin} / ${fmtMax}</span>
                </div>
                <div class="stat-val">
                    <span>Последнее:</span> <span>${fmtLast}</span>
                </div>
                <div class="stat-val trend ${trendClass}">
                    ${trendIcon} Тренд: ${trendSign}${fmtTrend}
                </div>
            </div>
            `;
        }).join('');

        container.innerHTML = `<div class="stats-grid">${rows}</div>`;
    }

    updateCharts(metricsData) {
        const now = Date.now();
        const minutes = this.getAttribute('minutes') || 30;
        const cutoff = now - minutes * 60 * 1000;

        // Обновляем хранилище данных и обновляем графики накопленными данными
        for (const [name, points] of Object.entries(metricsData)) {
            const chart = this.charts.get(name);
            if (!chart) continue;

            // Добавляем новые точки в хранилище (объединяем по timestamp)
            if (!this.metricsDataStore.has(name)) {
                this.metricsDataStore.set(name, []);
            }
            
            const existingData = this.metricsDataStore.get(name);
            const existingTimestamps = new Set(existingData.map(p => p.x));
            
            // Добавляем только новые точки
            for (const point of points) {
                const x = point.timestamp * 1000;
                if (!existingTimestamps.has(x)) {
                    existingData.push({ x, y: point.value });
                }
            }
            
            // Сортируем по времени
            existingData.sort((a, b) => a.x - b.x);
            
            // Удаляем старые точки за пределами окна
            while (existingData.length > 0 && existingData[0].x < cutoff) {
                existingData.shift();
            }
            
            // Обновляем график
            chart.data.datasets[0].data = existingData;
            chart.options.scales.x.min = cutoff;
            chart.options.scales.x.max = now;
            chart.update('none');
        }
    }

    getIcon(name) {
        const icons = {
            chart: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg>`,
            plus: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>`,
            check: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>`,
            refresh: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>`
        };
        return icons[name] || '';
    }

    render() {
        this.shadowRoot.innerHTML = `
        <style>
            :host {
                --bg-primary: #0f172a;
                --bg-card: #1e293b;
                --text-main: #f8fafc;
                --text-dim: #94a3b8;
                --accent: #38bdf8;
                --accent-green: #22c55e;
                --border-color: #334155;
                --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);            
                display: block;
                background: var(--bg-primary);
                color: var(--text-main);
                padding: 20px;
                min-height: 100vh;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }

            .header {
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 30px;
                flex-wrap: wrap;
                gap: 20px;
                position: relative;
            }

            .title h1 {
                margin: 0;
                font-size: 28px;
                letter-spacing: -0.5px;
                font-weight: 700;
            }

            .status-box {
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 13px;
                color: var(--text-dim);
                margin-top: 6px;
            }

            .status-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: #64748b;
                transition: all 0.3s;
            }

            .status-dot.online {
                background: #22c55e;
                box-shadow: 0 0 10px #22c55e;
            }

            .status-dot.error {
                background: #ef4444;
                box-shadow: 0 0 10px #ef4444;
            }

            .status-dot.connecting {
                background: #eab308;
                animation: pulse 2s infinite;
            }

            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }

            .metrics-selector {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-bottom: 30px;
            }

            .metric-chip {
                padding: 8px 16px;
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                border-radius: 20px;
                cursor: pointer;
                font-size: 13px;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
                user-select: none;
            }

            .metric-chip:hover {
                border-color: var(--accent);
                transform: translateY(-1px);
            }

            .metric-chip.active {
                background: var(--accent);
                border-color: var(--accent);
                color: #0f172a;
                font-weight: 600;
            }

            .charts-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(450px, 1fr));
                gap: 24px;
            }

            .chart-card {
                background: var(--bg-card);
                padding: 24px;
                border-radius: 16px;
                border: 1px solid var(--border-color);
                transition: all 0.3s;
                position: relative;
            }
                
            .chart-card:hover {
                box-shadow: var(--shadow);
                border-color: var(--accent);
                transform: translateY(-2px);
            }

            .chart-header {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 20px;
                padding-bottom: 12px;
                border-bottom: 1px solid var(--border-color);
            }

            .chart-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                background: rgba(56, 189, 248, 0.1);
                border-radius: 8px;
            }

            .chart-title {
                font-weight: 600;
                font-size: 14px;
                flex: 1;
                color: var(--text-main);
            }

            .chart-unit {
                font-size: 12px;
                color: var(--text-dim);
                background: rgba(148, 163, 184, 0.1);
                padding: 4px 8px;
                border-radius: 4px;
            }

            .canvas-container {
                height: 280px;
                position: relative;
            }

            .controls {
                display: flex;
                gap: 15px;
                align-items: flex-end;
                flex-wrap: wrap;
            }

            .control-group {
                display: flex;
                flex-direction: column;
                gap: 6px;
            }

            .control-group label {
                font-size: 12px;
                color: var(--text-dim);
                font-weight: 500;
            }

            input[type="number"] {
                background: var(--bg-card);
                border: 1px solid var(--border-color);
                color: var(--text-main);
                padding: 8px 12px;
                border-radius: 8px;
                width: 90px;
                font-size: 14px;
                transition: all 0.2s;
            }

            input[type="number"]:focus {
                outline: none;
                border-color: var(--accent);
                box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.1);
            }

            .apply-btn {
                background: var(--accent-green);
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 13px;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 6px;
                transition: all 0.2s;
                height: fit-content;
                margin-bottom: 2px;
            }

            .apply-btn:hover {
                background: #16a34a;
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(34, 197, 94, 0.3);
            }

            .apply-btn.pending {
                background: #eab308;
                animation: pulse-btn 2s infinite;
            }

            .apply-btn.pending:hover {
                background: #ca8a04;
            }

            @keyframes pulse-btn {
                0%, 100% { box-shadow: 0 0 0 0 rgba(234, 179, 8, 0.4); }
                50% { box-shadow: 0 0 0 8px rgba(234, 179, 8, 0); }
            }

            .notification {
                position: absolute;
                top: -50px;
                right: 0;
                background: var(--accent-green);
                color: white;
                padding: 10px 20px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 500;
                opacity: 0;
                transform: translateY(-10px);
                transition: all 0.3s;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            }

            .notification.show {
                opacity: 1;
                transform: translateY(0);
                top: 0;
            }

            .stats-container {
                margin-bottom: 30px;
                background: var(--bg-card);
                border-radius: 12px;
                padding: 16px;
                border: 1px solid var(--border-color);
            }

            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: 15px;
            }

            .stat-row {
                display: flex;
                flex-direction: column;
                gap: 4px;
                padding: 10px;
                background: rgba(0,0,0,0.2);
                border-radius: 8px;
                border-left: 3px solid var(--accent);
            }

            .stat-name {
                font-weight: 600;
                font-size: 12px;
                color: var(--text-dim);
                text-transform: uppercase;
            }

            .stat-val {
                font-size: 13px;
                display: flex;
                justify-content: space-between;
            }
            
            .stat-val b {
                color: var(--text-main);
            }

            .stats-empty {
                text-align: center;
                color: var(--text-dim);
                font-size: 14px;
                padding: 20px;
                font-style: italic;
            }

            .text-red { color: #ef4444; }
            .text-green { color: #22c55e; }

            @media (max-width: 768px) {
                .header {
                    flex-direction: column;
                }
                
                .charts-grid {
                    grid-template-columns: 1fr;
                }
                
                .controls {
                    width: 100%;
                }
            }
        </style>

        <div class="header">
            <div class="title">
                <h1>System Monitor</h1>
                <div class="status-box">
                    <div id="status-indicator" class="status-dot"></div>
                    <span id="status-text">Инициализация...</span>
                </div>
            </div>
            <div class="controls">
                <div class="control-group">
                    <label>Интервал (с)</label>
                    <input type="number" id="interval-input" value="20" min="5" max="300">
                </div>
                <div class="control-group">
                    <label>Глубина (мин)</label>
                    <input type="number" id="minutes-input" value="30" min="1" max="1440">
                </div>
                <button id="apply-params-btn" class="apply-btn">
                    ${this.getIcon('check')} Применено
                </button>
            </div>
            <div class="notification"></div>
        </div>

        <div class="metrics-selector"></div>
        <div class="charts-grid"></div>
        `;
    }
}

customElements.define('metrics-dashboard', MetricsDashboard);