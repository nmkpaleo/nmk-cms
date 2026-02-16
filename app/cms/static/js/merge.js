(function () {
  const root = document.querySelector('[data-merge-root]');
  if (!root) {
    return;
  }

  const searchForm = root.querySelector('[data-merge-search-form]');
  const resultsContainer = root.querySelector('[data-merge-results]');
  const statusContainer = root.querySelector('[data-merge-status]');
  const errorEl = root.querySelector('[data-merge-error]');
  const selectionContainer = root.querySelector('[data-merge-selection]');
  const selectionInputs = {
    source: root.querySelector('[data-merge-field="source"]'),
    target: root.querySelector('[data-merge-field="target"]')
  };
  const selectionDisplays = {
    source: root.querySelector('[data-merge-display="source"]'),
    target: root.querySelector('[data-merge-display="target"]')
  };
  const idsInput = root.querySelector('[data-merge-selected-ids]');
  const sourceList = root.querySelector('[data-merge-source-list]');
  const emptySources = root.querySelector('[data-merge-empty-sources]');
  const clearButtons = root.querySelectorAll('[data-merge-clear]');
  const resetButton = root.querySelector('[data-merge-reset]');
  const labelLookup = new Map();
  const resultTemplate = document.getElementById('merge-result-template');
  const compareTemplate = document.getElementById('merge-compare-template');

  let compareElement = null;

  const setStatus = (message, tone) => {
    if (!statusContainer) {
      return;
    }
    if (!message) {
      statusContainer.innerHTML = '';
      statusContainer.setAttribute('hidden', 'hidden');
      return;
    }

    statusContainer.removeAttribute('hidden');
    statusContainer.className = 'w3-container';
    let toneClass = 'w3-pale-blue w3-border-blue';
    if (tone === 'error') {
      toneClass = 'w3-pale-red w3-border-red';
    } else if (tone === 'info') {
      toneClass = 'w3-pale-yellow w3-border-amber';
    } else if (tone === 'success') {
      toneClass = 'w3-pale-green w3-border-green';
    }
    statusContainer.classList.add('w3-panel', 'w3-border', toneClass);
    statusContainer.textContent = message;
  };

  const clearError = () => {
    if (!errorEl) {
      return;
    }
    errorEl.textContent = '';
    errorEl.setAttribute('hidden', 'hidden');
  };

  const showError = (message) => {
    if (!errorEl) {
      setStatus(message, 'error');
      return;
    }
    errorEl.textContent = message;
    errorEl.removeAttribute('hidden');
  };

  const ensureCompareElement = () => {
    if (!compareTemplate) {
      return null;
    }
    if (compareElement && compareElement.isConnected) {
      return compareElement;
    }
    const fragment = compareTemplate.content.cloneNode(true);
    compareElement = fragment.querySelector('[data-merge-compare]');
    if (!compareElement) {
      return null;
    }
    if (selectionContainer && selectionContainer.parentNode) {
      selectionContainer.parentNode.insertBefore(fragment, selectionContainer.nextSibling);
    } else {
      root.appendChild(fragment);
    }
    return compareElement;
  };

  const renderComparison = () => {
    const sourcePreview = selectionInputs.source ? selectionInputs.source.dataset.preview : '';
    const targetPreview = selectionInputs.target ? selectionInputs.target.dataset.preview : '';

    if (!sourcePreview && !targetPreview) {
      if (compareElement && compareElement.parentNode) {
        compareElement.parentNode.removeChild(compareElement);
      }
      compareElement = null;
      return;
    }

    const element = ensureCompareElement();
    if (!element) {
      return;
    }

    const sourceList = element.querySelector('[data-merge-compare-source]');
    const targetList = element.querySelector('[data-merge-compare-target]');

    const populateList = (node, previewJson) => {
      if (!node) {
        return;
      }
      node.innerHTML = '';
      if (!previewJson) {
        const emptyItem = document.createElement('li');
        emptyItem.className = 'w3-text-grey';
        emptyItem.textContent = 'No data available';
        node.appendChild(emptyItem);
        return;
      }
      let preview;
      try {
        preview = JSON.parse(previewJson);
      } catch (error) {
        const errorItem = document.createElement('li');
        errorItem.className = 'w3-text-red';
        errorItem.textContent = 'Unable to parse preview details.';
        node.appendChild(errorItem);
        return;
      }
      preview.forEach((row) => {
        const item = document.createElement('li');
        item.textContent = `${row.field}: ${row.value}`;
        node.appendChild(item);
      });
    };

    populateList(sourceList, sourcePreview);
    populateList(targetList, targetPreview);
  };

  const normalizeList = (values) => {
    const seen = new Set();
    const normalized = [];
    values.forEach((value) => {
      const trimmed = (value || '').toString().trim();
      if (!trimmed || seen.has(trimmed)) {
        return;
      }
      seen.add(trimmed);
      normalized.push(trimmed);
    });
    return normalized;
  };

  const getState = () => {
    const targetId = (selectionInputs.target ? selectionInputs.target.value : '') || '';
    const selectedIds = normalizeList((idsInput ? idsInput.value : '').split(','));
    let sources = selectedIds.filter((id) => id !== targetId);

    const primarySource = (selectionInputs.source ? selectionInputs.source.value : '') || '';
    if (primarySource && primarySource !== targetId) {
      sources = [primarySource, ...sources.filter((id) => id !== primarySource)];
    }

    return { targetId, sources };
  };

  const renderSources = (sources) => {
    if (!sourceList) {
      return;
    }
    const primaryLabel = sourceList.dataset.primaryLabel || 'Primary';
    const removeLabel = sourceList.dataset.removeLabel || 'Remove';
    sourceList.innerHTML = '';
    if (!sources.length) {
      if (emptySources) {
        emptySources.removeAttribute('hidden');
        sourceList.appendChild(emptySources);
      }
      return;
    }

    if (emptySources) {
      emptySources.setAttribute('hidden', 'hidden');
    }

    sources.forEach((id, index) => {
      const listItem = document.createElement('li');
      listItem.className = 'w3-padding-small w3-border-bottom';
      const label = document.createElement('span');
      const labelText = labelLookup.get(id) || '';
      label.textContent = labelText ? `${labelText} (ID ${id})` : `ID ${id}`;
      listItem.appendChild(label);
      if (index === 0) {
        const badge = document.createElement('span');
        badge.className = 'w3-tag w3-round w3-blue w3-margin-left';
        badge.textContent = primaryLabel;
        listItem.appendChild(badge);
      }
      const removeButton = document.createElement('button');
      removeButton.type = 'button';
      removeButton.className = 'w3-button w3-small w3-light-grey w3-round w3-margin-left';
      removeButton.dataset.mergeRemoveSource = id;
      removeButton.innerHTML = `<span class="fa fa-times" aria-hidden="true"></span> <span class="w3-margin-left">${removeLabel}</span>`;
      listItem.appendChild(removeButton);
      sourceList.appendChild(listItem);
    });
  };

  const handleSourceRemoval = (id) => {
    const state = getState();
    state.sources = state.sources.filter((value) => value !== id);
    if (idsInput) {
      idsInput.value = normalizeList([state.targetId, ...state.sources.filter((value) => value !== state.targetId)]).join(',');
    }
    if (selectionInputs.source && selectionInputs.source.value === id) {
      delete selectionInputs.source.dataset.preview;
      delete selectionInputs.source.dataset.label;
    }
    updateDisplays(state);
  };

  const updateDisplays = (state) => {
    const primarySource = state.sources[0] || '';
    if (selectionInputs.source) {
      selectionInputs.source.value = primarySource;
    }
    if (selectionDisplays.source) {
      const sourceLabel = selectionInputs.source ? selectionInputs.source.dataset.label || '' : '';
      selectionDisplays.source.textContent = primarySource
        ? `${primarySource}${sourceLabel ? ` – ${sourceLabel}` : ''}`
        : '';
    }
    if (selectionInputs.target && selectionDisplays.target) {
      const targetLabel = selectionInputs.target.dataset.label || '';
      selectionDisplays.target.textContent = selectionInputs.target.value
        ? `${selectionInputs.target.value}${targetLabel ? ` – ${targetLabel}` : ''}`
        : '';
    }
    renderSources(state.sources);
    renderComparison();
  };

  const clearSelections = (role) => {
    if (role === 'sources') {
      if (idsInput) {
        idsInput.value = selectionInputs.target ? selectionInputs.target.value : '';
      }
      if (selectionInputs.source) {
        selectionInputs.source.value = '';
        delete selectionInputs.source.dataset.preview;
        delete selectionInputs.source.dataset.label;
      }
      updateDisplays({ targetId: selectionInputs.target ? selectionInputs.target.value : '', sources: [] });
      return;
    }

    const roles = role ? [role] : ['source', 'target'];
    roles.forEach((currentRole) => {
      const input = selectionInputs[currentRole];
      const display = selectionDisplays[currentRole];
      if (input) {
        input.value = '';
        delete input.dataset.preview;
        delete input.dataset.label;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      }
      if (display) {
        display.textContent = '';
      }
    });
    if (idsInput && (!role || role === 'source')) {
      idsInput.value = selectionInputs.target ? selectionInputs.target.value : '';
    }
    updateDisplays({ targetId: selectionInputs.target ? selectionInputs.target.value : '', sources: [] });
  };

  const renderResult = (result) => {
    if (!resultTemplate) {
      return;
    }
    const fragment = resultTemplate.content.cloneNode(true);
    const container = fragment.querySelector('[data-merge-result]');
    if (!container) {
      return;
    }

    const labelNode = container.querySelector('[data-merge-label]');
    const scoreNode = container.querySelector('[data-merge-score]');
    const idNode = container.querySelector('[data-merge-object-id]');
    const previewList = container.querySelector('[data-merge-preview]');

    const candidate = result.candidate || {};
    const preview = Array.isArray(result.preview) ? result.preview : [];

    if (labelNode) {
      labelNode.textContent = candidate.label || `Record ${candidate.pk ?? ''}`;
    }
    if (scoreNode) {
      scoreNode.textContent = `${Math.round((result.score || 0) * 10) / 10}`;
    }
    if (idNode) {
      idNode.textContent = candidate.pk ?? '';
    }
    if (previewList) {
      previewList.innerHTML = '';
      if (preview.length === 0) {
        const emptyItem = document.createElement('li');
        emptyItem.className = 'w3-text-grey';
        emptyItem.textContent = 'No preview fields configured.';
        previewList.appendChild(emptyItem);
      } else {
        preview.forEach((row) => {
          const item = document.createElement('li');
          item.textContent = `${row.field}: ${row.value}`;
          previewList.appendChild(item);
        });
      }
    }

    container.querySelectorAll('[data-merge-select]').forEach((button) => {
      button.addEventListener('click', () => {
        const role = button.dataset.mergeSelect;
        const state = getState();
        const candidateId = (candidate.pk || '').toString();

        if (candidateId) {
          labelLookup.set(candidateId, candidate.label || '');
        }

        if (role === 'target') {
          const previousTarget = state.targetId;
          state.targetId = candidateId;
          state.sources = state.sources.filter((id) => id !== candidateId);
          if (previousTarget && previousTarget !== candidateId) {
            state.sources = [previousTarget, ...state.sources.filter((id) => id !== previousTarget)];
          }
          if (selectionInputs.target) {
            selectionInputs.target.value = candidateId;
            selectionInputs.target.dataset.preview = JSON.stringify(preview);
            selectionInputs.target.dataset.label = candidate.label || '';
          }
        } else {
          state.sources = [candidateId, ...state.sources.filter((id) => id !== candidateId && id !== state.targetId)];
          if (selectionInputs.source) {
            selectionInputs.source.value = state.sources[0] || '';
            selectionInputs.source.dataset.preview = JSON.stringify(preview);
            selectionInputs.source.dataset.label = candidate.label || '';
          }
        }

        const allIds = normalizeList([state.targetId, ...state.sources.filter((id) => id !== state.targetId)]);
        if (idsInput) {
          idsInput.value = allIds.join(',');
        }

        if (selectionDisplays[role]) {
          const scoreLabel = result.score !== undefined ? ` (score ${Math.round(result.score)})` : '';
          selectionDisplays[role].textContent = `${candidateId} – ${candidate.label || ''}${scoreLabel}`;
        }

        updateDisplays(state);
      });
    });

    resultsContainer.appendChild(fragment);
  };

  const renderResults = (payload) => {
    resultsContainer.innerHTML = '';
    if (!payload || !Array.isArray(payload.results) || payload.results.length === 0) {
      setStatus('No candidates found for the supplied search.', 'info');
      return;
    }
    setStatus('Select a candidate to populate the merge form.', 'success');
    payload.results.forEach(renderResult);
  };

  const buildQueryParams = (form) => {
    const formData = new FormData(form);
    const params = new URLSearchParams();
    formData.forEach((value, key) => {
      if (value === null || value === undefined || value === '') {
        return;
      }
      params.append(key, value);
    });
    return params;
  };

  const fetchResults = async () => {
    if (!searchForm) {
      return;
    }
    clearError();
    setStatus('Searching for candidates…', 'info');
    const url = (searchForm.dataset.searchUrl || searchForm.getAttribute('action') || '').trim();
    if (!url) {
      showError('Search endpoint is not configured.');
      return;
    }
    const params = buildQueryParams(searchForm);
    try {
      const response = await fetch(`${url}?${params.toString()}`, {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin'
      });
      if (!response.ok) {
        let message = `Request failed with status ${response.status}`;
        try {
          const errorData = await response.json();
          if (errorData && errorData.detail) {
            message = errorData.detail;
          }
        } catch (error) {
          // ignore JSON parse errors and surface default message
        }
        throw new Error(message);
      }
      const payload = await response.json();
      renderResults(payload);
    } catch (error) {
      showError(error.message || 'Unable to fetch merge candidates.');
      resultsContainer.innerHTML = '';
      setStatus(null);
    }
  };

  if (searchForm) {
    searchForm.addEventListener('submit', (event) => {
      event.preventDefault();
      fetchResults();
    });
  }

  if (sourceList) {
    sourceList.addEventListener('click', (event) => {
      const button = event.target.closest('[data-merge-remove-source]');
      if (!button) {
        return;
      }
      event.preventDefault();
      handleSourceRemoval(button.dataset.mergeRemoveSource || '');
    });
  }

  clearButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const role = button.dataset.mergeClear;
      clearSelections(role);
    });
  });

  if (resetButton) {
    resetButton.addEventListener('click', () => {
      clearSelections();
      resultsContainer.innerHTML = '';
      setStatus(null);
      clearError();
    });
  }

  updateDisplays(getState());
})();
