/**
 * フォトブック管理アプリケーション - Web版
 * メインJavaScriptアプリケーション
 */

// アプリケーション状態
const AppState = {
    currentFolder: null,
    images: [],
    basket: [],
    selectedImages: new Set(),
    selectedBasketIndices: new Set(),
    labelPresets: {},
    previewData: []
};

// API エンドポイント
const API_BASE = 'http://127.0.0.1:5000/api';

// ログ出力
function log(message, level = 'info') {
    const logView = document.getElementById('logView');
    const logMessage = document.createElement('div');
    logMessage.className = `log-message ${level}`;

    const timestamp = new Date().toLocaleTimeString();
    const prefix = level === 'error' ? '[ERROR]' : level === 'warning' ? '[WARN]' : '[INFO]';

    logMessage.textContent = `${timestamp} ${prefix} ${message}`;
    logView.appendChild(logMessage);

    // 自動スクロール
    logView.scrollTop = logView.scrollHeight;
}

// API呼び出しヘルパー
async function apiCall(endpoint, method = 'GET', data = null) {
    try {
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json'
            }
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(`${API_BASE}${endpoint}`, options);

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'API call failed');
        }

        return await response.json();
    } catch (error) {
        log(`API エラー: ${error.message}`, 'error');
        throw error;
    }
}

// フォルダ選択モーダル
class FolderModal {
    constructor() {
        this.modal = document.getElementById('folderModal');
        this.currentPathInput = document.getElementById('currentPath');
        this.drivesList = document.getElementById('drivesList');
        this.subdirsList = document.getElementById('subdirsList');
        this.selectedPath = null;

        this.setupEventListeners();
    }

    setupEventListeners() {
        document.getElementById('closeFolderModal').addEventListener('click', () => this.close());
        document.getElementById('cancelFolderBtn').addEventListener('click', () => this.close());
        document.getElementById('selectFolderBtn').addEventListener('click', () => this.selectFolder());
    }

    async open() {
        this.modal.classList.add('show');
        await this.loadDrives();
    }

    close() {
        this.modal.classList.remove('show');
    }

    async loadDrives() {
        try {
            const data = await apiCall('/folder/list-drives');
            this.renderDrives(data.drives);
        } catch (error) {
            log('ドライブの取得に失敗しました', 'error');
        }
    }

    renderDrives(drives) {
        this.drivesList.innerHTML = '';

        drives.forEach(drive => {
            const item = document.createElement('div');
            item.className = 'drive-item';
            item.textContent = drive.name;
            item.dataset.path = drive.path;

            item.addEventListener('click', () => this.selectDrive(drive.path, item));

            this.drivesList.appendChild(item);
        });
    }

    async selectDrive(path, element) {
        // 選択状態を更新
        document.querySelectorAll('.drive-item').forEach(item => {
            item.classList.remove('selected');
        });
        element.classList.add('selected');

        this.selectedPath = path;
        this.currentPathInput.value = path;

        // サブディレクトリを読み込み
        await this.loadSubdirectories(path);
    }

    async loadSubdirectories(path) {
        try {
            const data = await apiCall('/folder/list-subdirs', 'POST', { path });
            this.renderSubdirectories(data.subdirs);
        } catch (error) {
            log('サブディレクトリの取得に失敗しました', 'error');
            this.subdirsList.innerHTML = '<div class="loading">アクセス権限がないか、エラーが発生しました</div>';
        }
    }

    renderSubdirectories(subdirs) {
        this.subdirsList.innerHTML = '';

        if (subdirs.length === 0) {
            this.subdirsList.innerHTML = '<div class="loading">サブフォルダはありません</div>';
            return;
        }

        subdirs.forEach(subdir => {
            const item = document.createElement('div');
            item.className = 'subdir-item';
            item.textContent = subdir.name;
            item.dataset.path = subdir.path;

            item.addEventListener('click', () => this.selectSubdir(subdir.path, item));

            this.subdirsList.appendChild(item);
        });
    }

    async selectSubdir(path, element) {
        // 選択状態を更新
        document.querySelectorAll('.subdir-item').forEach(item => {
            item.classList.remove('selected');
        });
        element.classList.add('selected');

        this.selectedPath = path;
        this.currentPathInput.value = path;

        // サブディレクトリを読み込み
        await this.loadSubdirectories(path);
    }

    async selectFolder() {
        if (!this.selectedPath) {
            log('フォルダが選択されていません', 'warning');
            return;
        }

        try {
            const data = await apiCall('/folder/browse', 'POST', { path: this.selectedPath });

            AppState.currentFolder = data.folder;
            AppState.images = data.images;
            AppState.selectedImages.clear();

            document.getElementById('folderPath').textContent = data.folder;

            renderThumbnails();
            this.close();

            log(`フォルダを開きました: ${data.folder} (${data.count}個の画像)`);
        } catch (error) {
            log('フォルダの読み込みに失敗しました', 'error');
        }
    }
}

// サムネイル表示
function renderThumbnails() {
    const grid = document.getElementById('thumbnailGrid');
    grid.innerHTML = '';

    if (AppState.images.length === 0) {
        grid.innerHTML = '<div class="loading">画像がありません</div>';
        return;
    }

    AppState.images.forEach((image, index) => {
        const item = document.createElement('div');
        item.className = 'thumbnail-item';
        item.dataset.index = index;
        item.dataset.path = image.path;

        // 選択状態を反映
        if (AppState.selectedImages.has(image.path)) {
            item.classList.add('selected');
        }

        // サムネイル画像（ローディング表示）
        const img = document.createElement('img');
        img.className = 'thumbnail-image';
        img.alt = image.name;
        img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="200"%3E%3Crect fill="%23f0f0f0" width="200" height="200"/%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" dy=".3em" fill="%23999"%3E読み込み中...%3C/text%3E%3C/svg%3E';

        // ファイル名
        const name = document.createElement('div');
        name.className = 'thumbnail-name';
        name.textContent = image.name;

        // 撮影日時
        const datetime = document.createElement('div');
        datetime.className = 'thumbnail-datetime';
        datetime.textContent = image.datetime ? new Date(image.datetime).toLocaleString('ja-JP') : '';

        item.appendChild(img);
        item.appendChild(name);
        item.appendChild(datetime);

        // クリックイベント（Ctrl+クリックで複数選択）
        item.addEventListener('click', (e) => {
            if (e.ctrlKey || e.metaKey) {
                // 複数選択
                toggleImageSelection(image.path, item);
            } else {
                // 単一選択
                AppState.selectedImages.clear();
                document.querySelectorAll('.thumbnail-item').forEach(el => {
                    el.classList.remove('selected');
                });
                AppState.selectedImages.add(image.path);
                item.classList.add('selected');
            }
        });

        grid.appendChild(item);

        // サムネイル画像を非同期で読み込み
        loadThumbnail(image.path, img);
    });
}

async function loadThumbnail(path, imgElement) {
    try {
        // パスをエンコード（先頭の / を除去）
        const encodedPath = encodeURIComponent(path.substring(1));
        const data = await apiCall(`/thumbnail/${encodedPath}`);
        imgElement.src = data.data;
    } catch (error) {
        imgElement.alt = 'エラー';
    }
}

function toggleImageSelection(path, element) {
    if (AppState.selectedImages.has(path)) {
        AppState.selectedImages.delete(path);
        element.classList.remove('selected');
    } else {
        AppState.selectedImages.add(path);
        element.classList.add('selected');
    }
}

// バスケットに追加
async function addToBasket() {
    if (AppState.selectedImages.size === 0) {
        log('画像が選択されていません', 'warning');
        return;
    }

    const items = Array.from(AppState.selectedImages).map(path => {
        const image = AppState.images.find(img => img.path === path);
        return {
            path: image.path,
            name: image.name,
            label: '全景',
            group: 1
        };
    });

    try {
        const data = await apiCall('/basket/add', 'POST', { items });
        AppState.basket = data.basket;
        renderBasket();
        log(`${items.length}個の画像をバスケットに追加しました`);
    } catch (error) {
        log('バスケットへの追加に失敗しました', 'error');
    }
}

// バスケット表示
function renderBasket() {
    const basketList = document.getElementById('basketList');
    basketList.innerHTML = '';

    if (AppState.basket.length === 0) {
        basketList.innerHTML = '<div class="loading">バスケットは空です</div>';
        updateBasketCount();
        return;
    }

    AppState.basket.forEach((item, index) => {
        const basketItem = document.createElement('div');
        basketItem.className = 'basket-item';
        basketItem.dataset.index = index;
        basketItem.dataset.path = item.path;

        // 選択状態を反映
        if (AppState.selectedBasketIndices.has(index)) {
            basketItem.classList.add('selected');
        }

        const text = document.createElement('div');
        text.className = 'basket-item-text';
        text.textContent = `${index + 1}. ${item.name} [${item.label}]`;

        basketItem.appendChild(text);

        // クリックイベント（Ctrl+クリックで複数選択）
        basketItem.addEventListener('click', (e) => {
            if (e.ctrlKey || e.metaKey) {
                // 複数選択
                toggleBasketSelection(index, basketItem);
            } else {
                // 単一選択
                AppState.selectedBasketIndices.clear();
                document.querySelectorAll('.basket-item').forEach(el => {
                    el.classList.remove('selected');
                });
                AppState.selectedBasketIndices.add(index);
                basketItem.classList.add('selected');
            }
        });

        basketList.appendChild(basketItem);
    });

    updateBasketCount();
}

function toggleBasketSelection(index, element) {
    if (AppState.selectedBasketIndices.has(index)) {
        AppState.selectedBasketIndices.delete(index);
        element.classList.remove('selected');
    } else {
        AppState.selectedBasketIndices.add(index);
        element.classList.add('selected');
    }
}

function updateBasketCount() {
    document.getElementById('countLabel').textContent = `選択数: ${AppState.basket.length}`;
}

// バスケット操作
async function moveBasketItemUp() {
    if (AppState.selectedBasketIndices.size !== 1) {
        log('1つのアイテムを選択してください', 'warning');
        return;
    }

    const index = Array.from(AppState.selectedBasketIndices)[0];
    if (index === 0) return;

    // 配列内で入れ替え
    [AppState.basket[index], AppState.basket[index - 1]] = [AppState.basket[index - 1], AppState.basket[index]];

    // 選択も移動
    AppState.selectedBasketIndices.clear();
    AppState.selectedBasketIndices.add(index - 1);

    await syncBasket();
    renderBasket();
}

async function moveBasketItemDown() {
    if (AppState.selectedBasketIndices.size !== 1) {
        log('1つのアイテムを選択してください', 'warning');
        return;
    }

    const index = Array.from(AppState.selectedBasketIndices)[0];
    if (index === AppState.basket.length - 1) return;

    // 配列内で入れ替え
    [AppState.basket[index], AppState.basket[index + 1]] = [AppState.basket[index + 1], AppState.basket[index]];

    // 選択も移動
    AppState.selectedBasketIndices.clear();
    AppState.selectedBasketIndices.add(index + 1);

    await syncBasket();
    renderBasket();
}

async function removeFromBasket() {
    if (AppState.selectedBasketIndices.size === 0) {
        log('削除するアイテムを選択してください', 'warning');
        return;
    }

    const index = Array.from(AppState.selectedBasketIndices)[0];
    const item = AppState.basket[index];

    try {
        const data = await apiCall('/basket/remove', 'POST', { path: item.path });
        AppState.basket = data.basket;
        AppState.selectedBasketIndices.clear();
        renderBasket();
        log('アイテムを削除しました');
    } catch (error) {
        log('削除に失敗しました', 'error');
    }
}

async function clearBasket() {
    if (AppState.basket.length === 0) return;

    if (!confirm('バスケットをすべてクリアしますか？')) return;

    try {
        await apiCall('/basket/clear', 'POST');
        AppState.basket = [];
        AppState.selectedBasketIndices.clear();
        renderBasket();
        clearPreview();
        log('バスケットをクリアしました');
    } catch (error) {
        log('クリアに失敗しました', 'error');
    }
}

async function syncBasket() {
    try {
        await apiCall('/basket/reorder', 'POST', { basket: AppState.basket });
    } catch (error) {
        log('バスケットの同期に失敗しました', 'error');
    }
}

// ラベル適用
async function applyLabelToSelected(label) {
    let paths = [];

    // バスケット内で選択されているアイテムを優先
    if (AppState.selectedBasketIndices.size > 0) {
        paths = Array.from(AppState.selectedBasketIndices).map(index => AppState.basket[index].path);
    } else if (AppState.selectedImages.size > 0) {
        // サムネイルグリッドで選択されている画像
        paths = Array.from(AppState.selectedImages);
    } else {
        log('ラベルを適用するアイテムを選択してください', 'warning');
        return;
    }

    try {
        const data = await apiCall('/basket/update-label', 'POST', { paths, label });
        AppState.basket = data.basket;
        renderBasket();
        log(`ラベル '${label}' を ${data.count} 個のアイテムに適用しました`);

        // サムネイルグリッドの選択をクリア
        AppState.selectedImages.clear();
        document.querySelectorAll('.thumbnail-item').forEach(el => {
            el.classList.remove('selected');
        });
    } catch (error) {
        log('ラベル適用に失敗しました', 'error');
    }
}

// ラベルプリセット読み込み
async function loadLabelPresets() {
    try {
        const data = await apiCall('/labels/presets');
        AppState.labelPresets = data.presets;

        const combo = document.getElementById('presetCombo');
        combo.innerHTML = '';

        Object.entries(AppState.labelPresets)
            .sort((a, b) => parseInt(a[0]) - parseInt(b[0]))
            .forEach(([number, label]) => {
                const option = document.createElement('option');
                option.value = label;
                option.textContent = `${number}. ${label}`;
                combo.appendChild(option);
            });
    } catch (error) {
        log('ラベルプリセットの読み込みに失敗しました', 'error');
    }
}

// 画像のソート
async function sortImages(mode) {
    try {
        const data = await apiCall('/images/sort', 'POST', { mode });
        AppState.images = data.images;
        renderThumbnails();
        log(`画像を並び替えました: ${mode}`);
    } catch (error) {
        log('並び替えに失敗しました', 'error');
    }
}

// プレビュー生成
async function generatePreview() {
    if (AppState.basket.length === 0) {
        log('バスケットが空です', 'warning');
        return;
    }

    const template = document.getElementById('templateInput').value.trim();
    if (!template) {
        log('テンプレートを入力してください', 'warning');
        return;
    }

    try {
        const data = await apiCall('/rename/preview', 'POST', { template });
        AppState.previewData = data.preview;
        renderPreview(data.preview);
        document.getElementById('executeBtn').disabled = false;
        log(`${data.count}件のプレビューを生成しました`);
    } catch (error) {
        log('プレビュー生成に失敗しました', 'error');
    }
}

function renderPreview(preview) {
    const tbody = document.querySelector('#previewTable tbody');
    tbody.innerHTML = '';

    preview.forEach(row => {
        const tr = document.createElement('tr');

        const oldNameTd = document.createElement('td');
        oldNameTd.textContent = row.old_name;

        const newNameTd = document.createElement('td');
        newNameTd.textContent = row.new_name;

        // 重複チェック
        if (row.exists) {
            newNameTd.classList.add('warning');
        } else if (row.old_name !== row.new_name) {
            newNameTd.classList.add('success');
        }

        tr.appendChild(oldNameTd);
        tr.appendChild(newNameTd);
        tbody.appendChild(tr);
    });
}

function clearPreview() {
    const tbody = document.querySelector('#previewTable tbody');
    tbody.innerHTML = '';
    AppState.previewData = [];
    document.getElementById('executeBtn').disabled = true;
}

// リネーム実行
async function executeRename() {
    if (AppState.previewData.length === 0) {
        log('プレビューを先に生成してください', 'warning');
        return;
    }

    if (!confirm(`${AppState.previewData.length}個のファイルをリネームしますか？`)) {
        return;
    }

    const template = document.getElementById('templateInput').value.trim();

    try {
        log('リネームを実行中...');
        const data = await apiCall('/rename/execute', 'POST', { template });

        log(`リネーム完了: 成功 ${data.success}件, 失敗 ${data.failed}件`);

        if (data.errors && data.errors.length > 0) {
            data.errors.forEach(error => log(error, 'error'));
        }

        if (data.success > 0) {
            alert(`${data.success}個のファイルをリネームしました。`);

            // バスケットとプレビューをクリア
            AppState.basket = [];
            AppState.selectedBasketIndices.clear();
            renderBasket();
            clearPreview();

            // 画像リストを再読み込み（サーバー側で更新済み）
            if (AppState.currentFolder) {
                const folderData = await apiCall('/folder/browse', 'POST', { path: AppState.currentFolder });
                AppState.images = folderData.images;
                renderThumbnails();
            }
        }
    } catch (error) {
        log('リネーム実行に失敗しました', 'error');
    }
}

// Undo
async function undoRename() {
    if (!confirm('直前のリネームを元に戻しますか？')) {
        return;
    }

    try {
        log('Undoを実行中...');
        const data = await apiCall('/rename/undo', 'POST');

        log(`Undo完了: 成功 ${data.success}件, 失敗 ${data.failed}件`);

        if (data.errors && data.errors.length > 0) {
            data.errors.forEach(error => log(error, 'error'));
        }

        if (data.success > 0) {
            alert(`${data.success}個のファイルを元に戻しました。`);

            // 画像リストを再読み込み
            if (AppState.currentFolder) {
                const folderData = await apiCall('/folder/browse', 'POST', { path: AppState.currentFolder });
                AppState.images = folderData.images;
                renderThumbnails();
            }
        }
    } catch (error) {
        log('Undo実行に失敗しました', 'error');
    }
}

// JSON出力
async function exportToJSON() {
    if (AppState.basket.length === 0) {
        log('バスケットが空です', 'warning');
        alert('バスケットにアイテムがありません。\n画像を選択してからJSON出力してください。');
        return;
    }

    try {
        const data = await apiCall('/export/json', 'POST');

        // JSONファイルとしてダウンロード
        const filename = `photobook_export_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();

        URL.revokeObjectURL(url);

        log(`JSON出力完了: ${filename} (${data.total_count}件)`);
        alert(`${data.total_count}件のアイテムをJSON出力しました。\n${filename}`);
    } catch (error) {
        log('JSON出力に失敗しました', 'error');
    }
}

// イベントリスナー設定
function setupEventListeners() {
    const folderModal = new FolderModal();

    // フォルダを開く
    document.getElementById('openFolderBtn').addEventListener('click', () => {
        folderModal.open();
    });

    // バスケットに追加
    document.getElementById('addToBasketBtn').addEventListener('click', addToBasket);

    // ソート
    document.getElementById('sortMode').addEventListener('change', (e) => {
        sortImages(e.target.value);
    });

    // バスケット操作
    document.getElementById('moveUpBtn').addEventListener('click', moveBasketItemUp);
    document.getElementById('moveDownBtn').addEventListener('click', moveBasketItemDown);
    document.getElementById('removeBtn').addEventListener('click', removeFromBasket);
    document.getElementById('clearBasketBtn').addEventListener('click', clearBasket);

    // ラベル適用
    document.getElementById('applyLabelBtn').addEventListener('click', () => {
        const label = document.getElementById('labelInput').value.trim() || '全景';
        applyLabelToSelected(label);
    });

    document.getElementById('applyPresetBtn').addEventListener('click', () => {
        const label = document.getElementById('presetCombo').value;
        if (label) {
            applyLabelToSelected(label);
        }
    });

    // リネーム操作
    document.getElementById('previewBtn').addEventListener('click', generatePreview);
    document.getElementById('executeBtn').addEventListener('click', executeRename);
    document.getElementById('undoBtn').addEventListener('click', undoRename);

    // JSON出力
    document.getElementById('exportJsonBtn').addEventListener('click', exportToJSON);

    // キーボードショートカット
    document.addEventListener('keydown', (e) => {
        // 数字キー 1-9 でラベル適用
        if (e.key >= '1' && e.key <= '9') {
            const number = parseInt(e.key);
            if (AppState.labelPresets[number]) {
                e.preventDefault();
                applyLabelToSelected(AppState.labelPresets[number]);
            }
        }

        // Delete キーで選択クリア
        if (e.key === 'Delete') {
            e.preventDefault();
            AppState.selectedImages.clear();
            document.querySelectorAll('.thumbnail-item').forEach(el => {
                el.classList.remove('selected');
            });
            log('画像の選択をクリアしました');
        }
    });
}

// 初期化
async function init() {
    log('アプリケーション起動');
    await loadLabelPresets();
    log(`ラベルプリセット: ${JSON.stringify(AppState.labelPresets)}`);
    setupEventListeners();
}

// DOMロード後に初期化
document.addEventListener('DOMContentLoaded', init);
