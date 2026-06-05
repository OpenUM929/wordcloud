// metadata_batch.js - 메타데이터 배치 처리 JavaScript

var currentStep = 1;
var uploadedData = null;
var columnMappings = {};
var fieldOrder = [];
var pseudonymFields = {};

var selectedField = null;
var isProcessing = false;

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function switchUploadTab(tab) {
    if (tab === 'file') {
        document.getElementById('fileUploadArea').style.display = 'block';
        document.getElementById('folderUploadArea').style.display = 'none';
        document.getElementById('tabFile').classList.add('btn-primary');
        document.getElementById('tabFile').classList.remove('btn-outline-secondary');
        document.getElementById('tabFolder').classList.remove('btn-primary');
        document.getElementById('tabFolder').classList.add('btn-outline-secondary');
    } else {
        document.getElementById('fileUploadArea').style.display = 'none';
        document.getElementById('folderUploadArea').style.display = 'block';
        document.getElementById('tabFolder').classList.add('btn-primary');
        document.getElementById('tabFolder').classList.remove('btn-outline-secondary');
        document.getElementById('tabFile').classList.remove('btn-primary');
        document.getElementById('tabFile').classList.add('btn-outline-secondary');
    }
}

function selectFolder() {
    var formData = new FormData();
    formData.append('folder', 'true');
    
    fetch('/api/batch/upload', {
        method: 'POST',
        body: formData
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.error) {
            document.getElementById('folderDetails').innerHTML = '<span style="color: red;">' + data.error + '</span>';
            document.getElementById('folderInfo').classList.remove('hidden');
            return;
        }
        
        uploadedData = data;
        columnMappings = {};
        fieldOrder = [];
        
        var fileCount = data.file_structures ? data.file_structures.length : 0;
        var fileCountText = fileCount > 1 ? fileCount + '개 파일' : '1개 파일';
        document.getElementById('folderDetails').innerHTML = '<strong>' + data.filename + '</strong> - ' + fileCountText + '<span style="color: #666; font-size: 11px; display: block; margin-top: 5px;">행: ' + data.rows + ', 공통 컬럼: ' + data.columns.length + '개</span>';
        document.getElementById('folderInfo').classList.remove('hidden');
        
        renderDataColumns();
        
        showStep(2);
    })
    .catch(function(error) {
        console.error('폴더 선택 오류:', error);
        document.getElementById('folderDetails').innerHTML = '<span style="color: red;">폴더 선택 중 오류가 발생했습니다.</span>';
        document.getElementById('folderInfo').classList.remove('hidden');
    });
}

function calculateSimilarity(str1, str2) {
    var words1 = str1.toLowerCase().split(/[_-]/);
    var words2 = str2.toLowerCase().split(/[_-]/);

    var commonWords = 0;
    words1.forEach(function(word1) {
        words2.forEach(function(word2) {
            if (word1.includes(word2) || word2.includes(word1)) {
                commonWords++;
            }
        });
    });

    var maxWords = Math.max(words1.length, words2.length);
    return maxWords > 0 ? commonWords / maxWords : 0;
}

var defaultMetadataStructure = {
    "session_id": { type: "string", required: true, auto: true, system: true, description: "세션 고유 식별자" },
    "created_at": { type: "timestamp", required: true, auto: true, system: true, description: "생성 시각" },
    "version": { type: "string", required: true, auto: true, system: true, description: "스키마 버전" },
    "target_employee_id": { type: "string", required: true, auto: false, system: false, pseudonymable: true, description: "평가 대상자 ID" },
    "target_employee_department": { type: "string", required: false, auto: true, system: false, pseudonymable: true, description: "평가 대상자 부서" },
    "target_employee_position": { type: "string", required: false, auto: true, system: false, pseudonymable: true, description: "평가 대상자 직책" },
    "total_evaluations": { type: "number", required: true, auto: true, system: false, description: "총 평가 수" },
    "evaluation_document": { type: "string", required: true, auto: false, system: false, description: "평가 문서 내용" },
    "evaluation_score": { type: "number", required: false, auto: false, system: false, description: "다면평가 점수 (기본 1점)" },
    "evaluator_department": { type: "string", required: false, auto: false, system: false, pseudonymable: true, description: "평가자 부서 정보" },
    "evaluator_position": { type: "string", required: false, auto: false, system: false, pseudonymable: true, description: "평가자 직책" },
    "evaluator_id": { type: "string", required: false, auto: false, system: false, pseudonymable: true, description: "평가자 ID" },
    "evaluation_date": { type: "string", required: false, auto: false, system: false, pseudonymable: true, description: "평가 일자" },
    "preprocessing_results": { type: "object", required: false, auto: true, system: false, description: "데이터 정제 결과" },
    "emotion_analysis_results": { type: "object", required: false, auto: true, system: false, description: "감정 분석 결과" },
    "leadership_analysis_results": { type: "object", required: false, auto: true, system: false, description: "리더십 분석 결과" },
    "nlp_analysis_results": { type: "object", required: false, auto: true, system: false, description: "NLP 분석 결과" },
    "consolidated_analysis": { type: "object", required: false, auto: true, system: false, description: "통합 분석 결과" },
    "leadership_consolidated": { type: "object", required: false, auto: true, system: false, description: "리더십 통합 분석 결과" },
    "wordcloud_path": { type: "string", required: false, auto: true, system: false, description: "워드클라우드 파일 경로" },
    "data_integrity_hash": { type: "string", required: true, auto: true, system: true, description: "데이터 무결성 해시" },
    "processing_status": { type: "object", required: true, auto: true, system: true, description: "처리 상태" },
    "evaluations": { type: "array", required: true, auto: true, system: false, description: "개별 평가 리스트" }
};

var metadataStructure = loadMetadataStructure();

function loadMetadataStructure() {
    var saved = localStorage.getItem('metadataStructure');
    if (saved) {
        try {
            var parsed = JSON.parse(saved);
            return Object.assign({}, defaultMetadataStructure, parsed);
        } catch (e) {
            console.error('메타데이터 구조 로드 실패:', e);
        }
    }
    return Object.assign({}, defaultMetadataStructure);
}

function saveMetadataStructure() {
    var userFields = {};
    Object.keys(metadataStructure).forEach(function(key) {
        if (!metadataStructure[key].system) {
            userFields[key] = metadataStructure[key];
        }
    });
    localStorage.setItem('metadataStructure', JSON.stringify(userFields));
}

function savePseudonymFieldsToLocal() {
    var active = {};
    Object.keys(pseudonymFields).forEach(function(f) {
        if (pseudonymFields[f]) active[f] = true;
    });
    try { localStorage.setItem('lastPseudonymFields', JSON.stringify(active)); } catch(e) {}
}

function restorePseudonymFieldsFromLocal() {
    try {
        var saved = localStorage.getItem('lastPseudonymFields');
        if (saved) {
            var parsed = JSON.parse(saved);
            Object.keys(parsed).forEach(function(f) {
                if (parsed[f]) pseudonymFields[f] = true;
            });
        }
    } catch(e) {}
}

function loadPreviousMapping() {
    var mappingStatus = document.getElementById('mappingStatus');

    if (!uploadedData || !uploadedData.columns) {
        var notificationDiv = document.createElement('div');
        notificationDiv.style.cssText = 'background: #f8d7da; padding: 10px; margin-bottom: 10px; border-radius: 5px; border-left: 4px solid #dc3545;';
        notificationDiv.innerHTML = '<strong>⚠️ 데이터 업로드 필요:</strong> 데이터를 먼저 업로드해주세요.';
        mappingStatus.insertBefore(notificationDiv, mappingStatus.firstChild);

        setTimeout(function() {
            if (notificationDiv.parentNode) {
                notificationDiv.parentNode.removeChild(notificationDiv);
            }
        }, 3000);
        return;
    }

    fetch('/api/mappings/last')
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (!data.success || !data.mappings) {
                var notificationDiv = document.createElement('div');
                notificationDiv.style.cssText = 'background: #fff3cd; padding: 10px; margin-bottom: 10px; border-radius: 5px; border-left: 4px solid #ffc107;';
                notificationDiv.innerHTML = '<strong>📂 이전 매핑 없음:</strong> 저장된 이전 매핑이 없습니다.';
                mappingStatus.insertBefore(notificationDiv, mappingStatus.firstChild);

                setTimeout(function() {
                    if (notificationDiv.parentNode) {
                        notificationDiv.parentNode.removeChild(notificationDiv);
                    }
                }, 3000);
                return;
            }

            var parsed = data.mappings;
            var currentColumnNames = uploadedData.columns.map(function(col) {
                return typeof col === 'string' ? col : col.name;
            });

            var appliedCount = 0;
            var failedFields = [];
            fieldOrder = [];
            
            Object.keys(parsed).forEach(function(field) {
                var mappedColumn = parsed[field];
                if (mappedColumn && currentColumnNames.indexOf(mappedColumn) !== -1) {
                    columnMappings[field] = mappedColumn;
                    fieldOrder.push(field);
                    appliedCount++;
                } else {
                    failedFields.push({ field: field, expectedColumn: mappedColumn || '(없음)' });
                }
            });

            renderMetadataTree();
            renderDataColumns();
            updateMappingStatus();

            var message = '';
            if (failedFields.length > 0) {
                message = '⚠️ ' + appliedCount + '개 적용, ' + failedFields.length + '개 실패 (현재 데이터에 없는 컬럼)';
            } else {
                message = '<strong>✅ 이전 매핑 불러오기 성공:</strong> ' + appliedCount + '개 필드가 모두 적용되었습니다.';
                style = 'background: #d4edda; padding: 10px; margin-bottom: 10px; border-radius: 5px; border-left: 4px solid #28a745;';
            }
            
            var notificationDiv = document.createElement('div');
            notificationDiv.style.cssText = style;
            notificationDiv.innerHTML = message;
            mappingStatus.insertBefore(notificationDiv, mappingStatus.firstChild);

            setTimeout(function() {
                if (notificationDiv.parentNode) {
                    notificationDiv.parentNode.removeChild(notificationDiv);
                }
                updateMappingStatus();
            }, 5000);
        })
        .catch(function(e) {
            console.error('이전 매핑 로드 실패:', e);
            var notificationDiv = document.createElement('div');
            notificationDiv.style.cssText = 'background: #f8d7da; padding: 10px; margin-bottom: 10px; border-radius: 5px; border-left: 4px solid #dc3545;';
            notificationDiv.innerHTML = '<strong>❌ 매핑 로드 실패:</strong> 이전 매핑 로드 중 오류가 발생했습니다.';
            mappingStatus.insertBefore(notificationDiv, mappingStatus.firstChild);

            setTimeout(function() {
                if (notificationDiv.parentNode) {
                    notificationDiv.parentNode.removeChild(notificationDiv);
                }
            }, 3000);
        });
}

function showStep(step) {
    console.log('showStep() called, step:', step, 'currentStep:', currentStep);
    
    if (step === currentStep) {
        console.log('이미 현재 단계인 경우 처리하지 않음');
        return;
    }
    
    var stepContents = document.querySelectorAll('.step-content');
    stepContents.forEach(function(content) {
        content.classList.add('hidden');
    });
    
    var stepElement = document.getElementById('step' + step);
    if (stepElement) {
        stepElement.classList.remove('hidden');
    }

    updateStepIndicators(step);

    currentStep = step;

    updateStepButtons();

    if (step === 2) {
        updateMappingStatus();
    }

    if (step === 3) {
        setTimeout(function() { generatePreview(); }, 100);
    }
}

function updateStepIndicators(activeStep) {
    var steps = document.querySelectorAll('.step');
    steps.forEach(function(stepElement) {
        var stepNum = parseInt(stepElement.dataset.step);
        stepElement.classList.remove('active', 'completed');

        if (stepNum < activeStep) {
            stepElement.classList.add('completed');
        } else if (stepNum === activeStep) {
            stepElement.classList.add('active');
        }
    });
}

function updateStepButtons() {
    var prevBtn = document.getElementById('prevBtn');
    var nextBtn = document.getElementById('nextBtn');
    var currentStepInfo = document.getElementById('current-step-info');

    if (prevBtn) {
        if (currentStep > 1) {
            prevBtn.style.display = 'inline-block';
        } else {
            prevBtn.style.display = 'none';
        }
    }

    if (nextBtn) {
        if (currentStep === 1) {
            var hasData = uploadedData && uploadedData.columns && uploadedData.columns.length > 0;
            if (hasData) {
                nextBtn.style.display = 'inline-block';
                nextBtn.disabled = false;
                nextBtn.textContent = '다음 단계';
                var existingNotice = document.querySelector('.auto-move-notice');
                if (existingNotice) {
                    existingNotice.remove();
                }
            } else {
                nextBtn.style.display = 'none';
                var stepButtons = document.querySelector('.step-buttons');
                if (stepButtons && !stepButtons.querySelector('.auto-move-notice')) {
                    var noticeDiv = document.createElement('div');
                    noticeDiv.className = 'auto-move-notice';
                    noticeDiv.style.cssText = 'color: #666; font-size: 14px; font-style: italic;';
                    noticeDiv.textContent = '파일 업로드를 하시면 완료 후 자동으로 다음 단계로 이동됩니다';
                    stepButtons.appendChild(noticeDiv);
                }
            }
        } else if (currentStep < 4) {
            nextBtn.style.display = 'inline-block';
            var existingNotice = document.querySelector('.auto-move-notice');
            if (existingNotice) {
                existingNotice.remove();
            }

            if (currentStep === 2) {
                var requiredFields = Object.keys(metadataStructure).filter(function(key) {
                    return metadataStructure[key].required && !metadataStructure[key].auto;
                });
                var missingRequiredFields = requiredFields.filter(function(key) { return !columnMappings[key]; });
                
                if (missingRequiredFields.length > 0) {
                    nextBtn.disabled = true;
                    nextBtn.textContent = '필수 매핑 필요 (' + missingRequiredFields.length + ')';
                    nextBtn.classList.remove('btn-primary');
                    nextBtn.classList.add('btn-danger');
                } else {
                    nextBtn.disabled = false;
                    nextBtn.textContent = '다음 단계';
                    nextBtn.classList.remove('btn-danger');
                    nextBtn.classList.add('btn-primary');
                }
            } else {
                nextBtn.disabled = false;
                nextBtn.textContent = '다음 단계';
            }
        } else {
            nextBtn.style.display = 'none';
            var existingNotice = document.querySelector('.auto-move-notice');
            if (existingNotice) {
                existingNotice.remove();
            }
        }
    }

    if (currentStepInfo) {
        var stepMessages = {
            1: '1단계: 데이터 업로드',
            2: '2단계: 메타데이터 매핑',
            3: '3단계: 미리보기',
            4: '4단계: 배치 처리 및 저장'
        };
        currentStepInfo.textContent = stepMessages[currentStep] || '';
    }
}

function renderMetadataTree() {
    var container = document.getElementById('metadataTree');
    container.innerHTML = '';
    
    var displayIndex = 0;
    Object.keys(metadataStructure).forEach(function(key) {
        var field = metadataStructure[key];
        if (field.auto) {
            return;
        }
        
        var orderNum = fieldOrder.indexOf(key) + 1;
        
        var item = document.createElement('div');
        item.className = 'tree-item';
        if (selectedField === key) {
            item.classList.add('selected');
        }
        if (orderNum > 0) {
            item.classList.add('mapped');
        }
        
        var orderHtml = orderNum > 0 ? '<span class="tree-order">#' + orderNum + '</span>' : '<span class="tree-order"></span>';
        var requiredHtml = field.required ? '<span class="tree-required">*필수</span>' : '';
        var autoHtml = field.auto ? '<span class="tree-auto">자동생성</span>' : '';
        
        var pseudoHtml = '';
        if (field.pseudonymable) {
            pseudoHtml = '<span class="pseudo-toggle" title="항상 가명처리됨">🔒 가명</span>';
        }
        
        item.innerHTML = orderHtml + '<span class="tree-key">' + key + '</span><span class="tree-type">(' + field.type + ')</span>' + requiredHtml + autoHtml + ' ' + pseudoHtml;
        item.onclick = (function(k) { return function() { selectField(k); }; })(key);
        container.appendChild(item);
    });
}

function renderDataColumns() {
    var container = document.getElementById('dataColumns');
    container.innerHTML = '';
    
    if (!uploadedData || !uploadedData.columns) return;
    
    var columns = uploadedData.columns.map(function(col) {
        return typeof col === 'string' ? {name: col, type: 'string', sample: ''} : col;
    });
    
    columns.forEach(function(column) {
        var mappedField = Object.keys(columnMappings).find(function(field) { return columnMappings[field] === column.name; });
        var orderNum = mappedField ? (fieldOrder.indexOf(mappedField) + 1) : 0;
        
        var item = document.createElement('div');
        item.className = 'column-row';
        if (orderNum > 0) {
            item.classList.add('mapped');
        }
        
        var orderHtml = orderNum > 0 ? '<span class="column-order">#' + orderNum + '</span>' : '';
        var mappingInfo = mappedField ? '<span class="column-mapping">→ ' + mappedField + '</span>' : '';
        
        item.innerHTML = '<span class="column-name">' + column.name + '</span><span class="column-type">(' + column.type + ')</span>' + orderHtml + mappingInfo + '<span class="column-sample">' + (column.sample || '') + '</span>';
        item.onclick = (function(col) { return function() { selectDataColumn(col); }; })(column);
        container.appendChild(item);
    });
}

function selectField(key) {
    selectedField = key;
    renderMetadataTree();
    renderDataColumns();
    updateSelectedFieldInfo();
}

function selectDataColumn(column) {
    if (!selectedField) return;
    
    if (columnMappings[selectedField] === column.name) {
        delete columnMappings[selectedField];
        fieldOrder = fieldOrder.filter(function(f) { return f !== selectedField; });
    } else {
        Object.keys(columnMappings).forEach(function(field) {
            if (columnMappings[field] === column.name) {
                delete columnMappings[field];
                fieldOrder = fieldOrder.filter(function(f) { return f !== field; });
            }
        });
        columnMappings[selectedField] = column.name;
        if (fieldOrder.indexOf(selectedField) === -1) {
            fieldOrder.push(selectedField);
        }
    }
    
    renderMetadataTree();
    renderDataColumns();
    updateMappingStatus();
}

function updateSelectedFieldInfo() {
    var container = document.getElementById('selectedFieldInfo');
    var description = document.getElementById('fieldDescription');
    
    if (!selectedField) {
        container.innerHTML = '';
        description.value = '';
        return;
    }
    
    var field = metadataStructure[selectedField];
    var mappedInfo = columnMappings[selectedField] || '미매핑';
    
    container.innerHTML = '<p><strong>필드명:</strong> ' + selectedField + '</p><p><strong>타입:</strong> ' + field.type + '</p><p><strong>필수:</strong> ' + (field.required ? '예' : '아니오') + '</p><p><strong>자동생성:</strong> ' + (field.auto ? '예' : '아니오') + '</p><p><strong>설명:</strong> ' + field.description + '</p><p><strong>매핑된 열:</strong> ' + mappedInfo + '</p>';
    description.value = field.description;
}

function updateMappingStatus() {
    var container = document.getElementById('mappingStatus');
    
    var requiredFields = Object.keys(metadataStructure).filter(function(key) {
        return metadataStructure[key].required && !metadataStructure[key].auto;
    });
    
    var mappedRequiredFields = requiredFields.filter(function(key) { return !!columnMappings[key]; });
    
    var mappingListHtml = '';
    Object.keys(columnMappings).forEach(function(field) {
        mappingListHtml += '<li>' + field + ' → ' + columnMappings[field] + '</li>';
    });
    
    container.innerHTML = '<p><strong>필수 필드 매핑:</strong> ' + mappedRequiredFields.length + '/' + requiredFields.length + '</p><p><strong>전체 필드 매핑:</strong> ' + Object.keys(columnMappings).length + '/' + Object.keys(metadataStructure).length + '</p><ul>' + mappingListHtml + '</ul>';
    
    if (currentStep === 2) {
        updateStepButtons();
    }
    
    var pseudoDisplay = document.getElementById('pseudonymFieldsDisplay');
    if (pseudoDisplay) {
        pseudoDisplay.innerHTML = '🔒 모든 PII 필드가 항상 가명처리됩니다';
    }
}

function showAddFieldForm() {
    document.getElementById('fieldForm').classList.remove('hidden');
}

function cancelFieldEdit() {
    document.getElementById('fieldForm').classList.add('hidden');
}

function saveField() {
    var name = document.getElementById('fieldName').value.trim();
    var type = document.getElementById('fieldType').value;
    var required = document.getElementById('fieldRequired').checked;
    var description = document.getElementById('fieldDescriptionInput').value.trim();
    
    if (!name) {
        alert('필드명을 입력하세요.');
        return;
    }
    
    if (metadataStructure[name]) {
        alert('이미 존재하는 필드입니다.');
        return;
    }
    
    metadataStructure[name] = {
        type: type,
        required: required,
        auto: false,
        system: false,
        description: description
    };
    
    saveMetadataStructure();
    renderMetadataTree();
    cancelFieldEdit();
}

function prevStep() {
    if (currentStep > 1) {
        showStep(currentStep - 1);
    }
}

var isNextStepProcessing = false;

function nextStep() {
    console.log('nextStep() called, currentStep:', currentStep, 'isProcessing:', isNextStepProcessing);
    
    if (isNextStepProcessing) {
        console.log('nextStep() already processing, ignoring');
        return;
    }
    
    isNextStepProcessing = true;
    
    try {
        if (currentStep === 1) {
            if (!uploadedData) {
                alert('파일을 먼저 업로드해주세요.');
                isNextStepProcessing = false;
                return;
            }
            showStep(2);
        } else if (currentStep === 2) {
            var requiredFields = Object.keys(metadataStructure).filter(function(key) {
                return metadataStructure[key].required && !metadataStructure[key].auto;
            });
            
            var missingRequiredFields = requiredFields.filter(function(key) { return !columnMappings[key]; });
            
            if (missingRequiredFields.length > 0) {
                alert('필수 필드 매핑이 완료되지 않았습니다: ' + missingRequiredFields.join(', '));
                isNextStepProcessing = false;
                return;
            }
            
            fetch('/api/mappings/save', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({mappings: columnMappings})
            }).then(function(resp) {
                return resp.json();
            }).then(function(data) {
                if (!data.success) {
                    console.warn('매핑 저장 실패(계속 진행):', data.error || '알 수 없는 오류');
                } else {
                    console.log('매핑 저장 성공');
                }
            }).catch(function(e) { console.error('매핑 저장 실패:', e); });
            
            currentStep = 3;
            updateStepIndicators(3);
            document.getElementById('step2').classList.add('hidden');
            document.getElementById('step3').classList.remove('hidden');
            updateStepButtons();
            setTimeout(function() { generatePreview(); }, 100);
        } else if (currentStep === 3) {
            currentStep = 4;
            updateStepIndicators(4);
            document.getElementById('step3').classList.add('hidden');
            document.getElementById('step4').classList.remove('hidden');
            updateStepButtons();
        }
    } finally {
        setTimeout(function() {
            isNextStepProcessing = false;
            console.log('nextStep() processing completed');
        }, 100);
    }
}

function generatePreview() {
    console.log('=== 미리보기 생성 시작 ===');
    var container = document.getElementById('previewResults');
    container.innerHTML = '';
    
    console.log('uploadedData:', uploadedData);
    console.log('columnMappings:', columnMappings);
    console.log('currentStep (before generatePreview):', currentStep);
    
    if (!uploadedData) {
        container.innerHTML = '<p style="color: red;">❌ 오류: 데이터가 업로드되지 않았습니다.</p>';
        return;
    }
    
    if (Object.keys(columnMappings).length === 0) {
        container.innerHTML = '<p style="color: orange;">⚠️ 경고: 메타데이터 매핑이 완료되지 않았습니다.</p>';
        return;
    }
    
    var targetIdColumn = columnMappings['target_employee_id'];
    
    if (!targetIdColumn) {
        container.innerHTML = '<p style="color: red;">❌ 오류: target_employee_id 필드가 매핑되지 않았습니다.</p>';
        return;
    }
    
    var previewData = uploadedData.preview_rows || uploadedData.preview_data;
    
    if (!previewData || previewData.length === 0) {
        container.innerHTML = '<p style="color: red;">❌ 오류: 미리보기 데이터가 없습니다.</p>';
        return;
    }
    
    if (uploadedData.file_structures && uploadedData.file_structures.length > 1) {
        var structures = uploadedData.file_structures;
        var firstCols = structures[0].columns || [];
        
        var hasMixedStructures = structures.some(function(s) {
            var cols = s.columns || [];
            return cols.length !== firstCols.length || !cols.every(function(c) { return firstCols.indexOf(c) !== -1; });
        });
        
        if (hasMixedStructures) {
            var warningDiv = document.createElement('div');
            warningDiv.style.cssText = 'background: #fff3cd; border: 1px solid #ffc107; border-radius: 5px; padding: 15px; margin-bottom: 15px;';
            warningDiv.innerHTML = '<h4 style="color: #856404; margin-top: 0;">⚠️ 파일 구조 불일치 경고</h4><p style="color: #856404;">선택한 폴더의 파일들이 서로 다른 컬럼 구조를 가지고 있습니다.</p>';
            container.appendChild(warningDiv);
        }
    }
    
    try {
        var groupedData = {};
        
        previewData.forEach(function(row) {
            var sourceFile = row._source_file || '(알 수 없음)';
            var targetId = row[targetIdColumn];
            
            if (!targetId) return;
            
            if (!groupedData[targetId]) {
                groupedData[targetId] = {
                    rows: [],
                    sources: new Set()
                };
            }
            groupedData[targetId].rows.push(row);
            if (sourceFile) {
                groupedData[targetId].sources.add(sourceFile);
            }
        });
        
        console.log('groupedData:', groupedData);
        
        if (Object.keys(groupedData).length === 0) {
            container.innerHTML += '<p>대상자 ID별로 그룹화된 데이터가 없습니다.</p>';
            return;
        }
        
        Object.keys(groupedData).forEach(function(targetId) {
            var data = groupedData[targetId];
            var sourceCount = data.sources.size;
            
            var employeeDiv = document.createElement('div');
            employeeDiv.className = 'employee-preview';
            employeeDiv.style.cssText = 'border: 1px solid #ddd; border-radius: 5px; padding: 15px; margin: 10px 0; background-color: #f9f9f9;';
            
            var sourceInfo = sourceCount > 1 ? '<span style="background: #17a2b8; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px;">' + sourceCount + '개 파일</span>' : '';
            
            if (columnMappings['evaluation_document']) {
                var sampleHtml = '';
                data.rows.slice(0, 3).forEach(function(row) {
                    var evalDoc = row[columnMappings['evaluation_document']] || '';
                    sampleHtml += '<li style="font-size: 12px; margin: 5px 0;">' + evalDoc.substring(0, 100) + (evalDoc.length > 100 ? '...' : '') + '</li>';
                });
                
                employeeDiv.innerHTML = '<h4 style="margin-top: 0; color: #007bff;">👤 대상자 ID: ' + targetId + ' ' + sourceInfo + '</h4><p><strong>평가수:</strong> ' + data.rows.length + '개</p><div style="margin-top: 10px; padding: 10px; background-color: white; border-radius: 3px;"><h5 style="margin: 0 0 10px 0; color: #333;">샘플 평가:</h5><ul style="margin: 0; padding-left: 20px;">' + sampleHtml + '</ul>' + (data.rows.length > 3 ? '<p style="font-size: 12px; color: #666; margin-top: 5px;">+' + (data.rows.length - 3) + '개의 평가...</p>' : '') + '</div>';
            } else {
                employeeDiv.innerHTML = '<h4 style="margin-top: 0; color: #007bff;">👤 대상자 ID: ' + targetId + '</h4><p><strong>평가수:</strong> ' + data.rows.length + '개</p>';
            }
            container.appendChild(employeeDiv);
        });
        
        console.log('generatePreview completed, currentStep:', currentStep);
    } catch (error) {
        console.error('미리보기 생성 오류:', error);
        container.innerHTML = '<p style="color: red;">❌ 오류: ' + error.message + '</p>';
    }
}

function startBatchProcessing() {
    if (isProcessing) {
        alert('이미 처리 중입니다.');
        return;
    }
    
    var requiredFields = Object.keys(metadataStructure).filter(function(key) {
        return metadataStructure[key].required && !metadataStructure[key].auto;
    });
    
    var missingRequiredFields = requiredFields.filter(function(key) { return !columnMappings[key]; });
    
    if (missingRequiredFields.length > 0) {
        alert('필수 필드 매핑이 완료되지 않았습니다: ' + missingRequiredFields.join(', '));
        return;
    }
    
    isProcessing = true;
    document.getElementById('processingStatus').classList.remove('hidden');
    
    var settings = {
        enablePreprocessing: document.getElementById('enablePreprocessing').checked,
        enableEmotionAnalysis: document.getElementById('enableEmotionAnalysis').checked,
        mappings: columnMappings,
    };
    
    var eventSource = new EventSource('/api/batch/events');
    
    eventSource.onopen = function() {
        console.log('SSE 연결 성공');
    };
    
    eventSource.onmessage = function(event) {
        if (!event.data || event.data.trim() === '') return;
        var data;
        try { data = JSON.parse(event.data); } catch(e) { return; }
        
        if (data.step !== undefined) {
            var steps = [
                '파일 로드 중...',
                '메타데이터 생성 중...',
                'imeta 저장 중...',
                'tmeta 저장 중...',
                '워드클라우드 생성 중...',
                '처리 완료'
            ];
            
            var currentStep = data.step;
            document.getElementById('processingText').textContent = steps[currentStep] || '';
            
            var procSteps = document.querySelectorAll('.proc-step');
            procSteps.forEach(function(step, index) {
                if (index < currentStep) {
                    step.classList.add('completed');
                    step.classList.remove('active');
                } else if (index === currentStep) {
                    step.classList.add('active');
                    step.classList.remove('completed');
                } else {
                    step.classList.remove('active', 'completed');
                }
            });
            
            if (data.progress !== undefined) {
                document.getElementById('progressFill').style.width = data.progress + '%';
            } else {
                var progress = (currentStep + 1) * 10;
                document.getElementById('progressFill').style.width = progress + '%';
            }
        }
        
        if (data.log) {
            console.log(data.log);
        }
        
        if (data.completed) {
            eventSource.close();
            document.getElementById('progressFill').style.width = '100%';
            document.getElementById('processingText').textContent = '처리 완료!';
            
            var procSteps = document.querySelectorAll('.proc-step');
            procSteps.forEach(function(step) {
                step.classList.remove('active');
            });
            
            var lastStep = procSteps[procSteps.length - 1];
            if (lastStep) {
                lastStep.classList.add('completed');
            }
            
            setTimeout(function() {
                document.getElementById('processingResults').classList.remove('hidden');
                var hasFailures = data.failed_employees && data.failed_employees.length > 0;
                var failedListHtml = '';
                if (hasFailures) {
                    var btn = document.getElementById('retryFailedBtn');
                    btn.style.display = 'inline-block';
                    btn.dataset.failedEmployees = JSON.stringify(data.failed_employees);
                    failedListHtml = '<div style="margin-top: 10px; padding: 10px; background: #f8d7da; border-radius: 5px;"><strong style="color: #721c24;">실패 상세:</strong>';
                    data.failed_employees.forEach(function(emp) {
                        failedListHtml += '<div style="margin-top: 5px;"><strong>' + escapeHtml(emp.employee_id) + ':</strong> ' + escapeHtml(emp.error) + '</div>';
                    });
                    failedListHtml += '</div>';
                }
                var html = '<div class="status-success"><h4>✅ 배치 처리<br>완료</h4><div style="margin-top: 15px;"><table style="width: 100%; border-collapse: collapse; border: 1px solid #dee2e6;"><thead><tr style="background: #f8f9fa;"><th style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold; text-align: center;">총 처리된 행</th><th style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold; text-align: center;">고유 직원 수</th><th style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold; text-align: center;">성공한 직원</th><th style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold; text-align: center;">실패한 직원</th><th style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold; text-align: center;">비속어 발견 직원</th></tr></thead><tbody><tr style="background: #ffffff;"><td style="padding: 12px; border: 1px solid #dee2e6; text-align: center; font-weight: bold; color: #007bff;">' + (data.total_rows || data.total_processed || 0) + '</td><td style="padding: 12px; border: 1px solid #dee2e6; text-align: center; font-weight: bold; color: #6c757d;">' + (data.total_employees || data.unique_employees || 0) + '</td><td style="padding: 12px; border: 1px solid #dee2e6; text-align: center; font-weight: bold; color: #28a745;">' + (data.success_count || 0) + '</td><td style="padding: 12px; border: 1px solid #dee2e6; text-align: center; font-weight: bold; color: #dc3545;">' + (data.error_count || 0) + '</td><td style="padding: 12px; border: 1px solid #dee2e6; text-align: left; color: #ffc107;">' + (data.profanity_employees && data.profanity_employees.length > 0 ? data.profanity_employees.map(function(emp) { return '<div style="margin-bottom: 5px;"><strong>' + escapeHtml(emp.employee_id) + ':</strong> ' + escapeHtml(emp.profanities.join(', ')) + '</div>'; }).join('') : '없음') + '</td></tr></tbody></table>' + failedListHtml + '</div></div>';
                document.getElementById('resultsSummary').innerHTML = html;
            }, 500);
            
            isProcessing = false;
        }
        
        if (data.error) {
            eventSource.close();
            alert(data.error);
            isProcessing = false;
        }
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE 오류:', error);
        eventSource.close();
        isProcessing = false;
    };
    
    fetch('/api/batch/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.error) {
            eventSource.close();
            alert(data.error);
            isProcessing = false;
        } else if (data.batch_dir) {
            sessionStorage.setItem('batchDir', data.batch_dir);
        }
    })
    .catch(function(error) {
        console.error('배치 처리 오류:', error);
        eventSource.close();
        alert('배치 처리 중 오류가 발생했습니다.');
        isProcessing = false;
    });
}

function downloadResults() {
    fetch('/api/batch/download')
    .then(function(response) { return response.blob(); })
    .then(function(blob) {
        var url = window.URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'batch_results_' + new Date().toISOString().slice(0, 19).replace(/:/g, '') + '.zip';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    })
    .catch(function(error) {
        console.error('다운로드 오류:', error);
        alert('결과 다운로드 중 오류가 발생했습니다.');
    });
}

function retryFailed() {
    var btn = document.getElementById('retryFailedBtn');
    var failedEmployees = JSON.parse(btn.dataset.failedEmployees || '[]');
    if (failedEmployees.length === 0) return;

    var empIds = failedEmployees.map(function(e) { return e.employee_id; });
    if (!confirm('실패한 ' + empIds.length + '건을 재배치하시겠습니까?')) return;

    var processingDiv = document.getElementById('processingStatus');
    processingDiv.classList.remove('hidden');
    document.getElementById('processingText').textContent = '재배치 준비 중...';

    fetch('/api/batch/retry-failed', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            employee_ids: empIds,
            mappings: columnMappings,
            enableEmotionAnalysis: document.getElementById('enableEmotionAnalysis').checked,
            enablePreprocessing: document.getElementById('enablePreprocessing').checked,
        })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (data.success) {
            alert('재배치 완료! 성공: ' + (data.success_count || 0) + ', 실패: ' + (data.error_count || 0));
            btn.style.display = 'none';
            document.getElementById('processingResults').classList.add('hidden');
        } else {
            alert('재배치 실패: ' + (data.error || '알 수 없는 오류'));
        }
    })
    .catch(function(e) {
        alert('재배치 중 오류 발생: ' + e.message);
    })
    .finally(function() {
        processingDiv.classList.add('hidden');
    });
}

function deleteBatch() {
    if (!confirm('정말로 배치 처리 결과를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) {
        return;
    }

    var batchPath = sessionStorage.getItem('batchDir');

    if (!batchPath) {
        var batchResults = sessionStorage.getItem('batchResults');
        if (batchResults) {
            try {
                var results = JSON.parse(batchResults);
                if (results.batch_dir) {
                    batchPath = results.batch_dir;
                }
            } catch (e) {
                console.error('배치 결과 파싱 오류:', e);
            }
        }
    }

    if (!batchPath) {
        alert('삭제할 배치 경로를 찾을 수 없습니다. 먼저 배치 처리를 완료해주세요.');
        return;
    }

    var batchId = batchPath.split(/[\\/]/).pop();
    fetch('/api/perspective/batch/' + batchId, {
        method: 'DELETE'
    })
    .then(function(response) { return response.json(); })
    .then(function(data) {
        if (data.success) {
            alert('배치 처리 결과가 성공적으로 삭제되었습니다.');
            sessionStorage.removeItem('batchResults');
            document.getElementById('processingResults').classList.add('hidden');
            document.getElementById('processingStatus').classList.add('hidden');
            showStep(1);
        } else {
            alert('오류: ' + data.error);
        }
    })
    .catch(function(error) {
        console.error('삭제 오류:', error);
        alert('배치 결과 삭제 중 오류가 발생했습니다.');
    });
}

function showMappingManager() {
    var modal = document.getElementById('mappingManagerModal');
    var listContainer = document.getElementById('mappingList');
    modal.style.display = 'block';
    listContainer.innerHTML = '<p style="color: #666;">매핑 목록을 불러오는 중...</p>';
    
    fetch('/api/mappings/list')
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (!data.success || !data.files || data.files.length === 0) {
                listContainer.innerHTML = '<p style="color: #999;">저장된 매핑이 없습니다.</p>';
                return;
            }
            
            var html = '<table style="width: 100%; border-collapse: collapse;">';
            html += '<thead><tr style="background: #f8f9fa;"><th style="padding: 10px; border: 1px solid #ddd;">날짜/시간</th><th style="padding: 10px; border: 1px solid #ddd;">크기</th><th style="padding: 10px; border: 1px solid #ddd;">작업</th></tr></thead>';
            html += '<tbody>';
            
            data.files.forEach(function(file) {
                var date = new Date(file.modified * 1000);
                var dateStr = date.toLocaleString('ko-KR');
                var sizeStr = file.size < 1024 ? file.size + ' B' : (file.size / 1024).toFixed(1) + ' KB';
                
                html += '<tr>';
                html += '<td style="padding: 10px; border: 1px solid #ddd;">' + file.display_name + '</td>';
                html += '<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">' + sizeStr + '</td>';
                html += '<td style="padding: 10px; border: 1px solid #ddd; text-align: center;">';
                html += '<button class="btn btn-primary btn-sm" onclick="loadMappingByName(\'' + file.name + '\')" style="margin-right: 5px;">선택</button>';
                html += '<button class="btn btn-danger btn-sm" onclick="deleteMappingByName(\'' + file.name + '\')">삭제</button>';
                html += '</td>';
                html += '</tr>';
            });
            
            html += '</tbody></table>';
            listContainer.innerHTML = html;
        })
        .catch(function(e) {
            listContainer.innerHTML = '<p style="color: red;">매핑 목록 로드 실패</p>';
        });
}

function closeMappingManager() {
    document.getElementById('mappingManagerModal').style.display = 'none';
}

function loadMappingByName(name) {
    fetch('/api/mappings/load/' + encodeURIComponent(name))
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (!data.success) {
                alert('매핑 로드 실패: ' + (data.error || '알 수 없는 오류'));
                return;
            }
            
            if (!uploadedData || !uploadedData.columns) {
                alert('데이터를 먼저 업로드해주세요.');
                return;
            }
            
            var parsed = data.mappings;
            var currentColumnNames = uploadedData.columns.map(function(col) {
                return typeof col === 'string' ? col : col.name;
            });

            var appliedCount = 0;
            var failedFields = [];
            fieldOrder = [];
            
            Object.keys(parsed).forEach(function(field) {
                var mappedColumn = parsed[field];
                if (mappedColumn && currentColumnNames.indexOf(mappedColumn) !== -1) {
                    columnMappings[field] = mappedColumn;
                    fieldOrder.push(field);
                    appliedCount++;
                } else {
                    failedFields.push({ field: field, expectedColumn: mappedColumn || '(없음)' });
                }
            });

            renderMetadataTree();
            renderDataColumns();
            updateMappingStatus();

            var message = '';
            if (failedFields.length > 0) {
                message = '⚠️ ' + appliedCount + '개 적용, ' + failedFields.length + '개 실패 (현재 데이터에 없는 컬럼)';
            } else {
                message = '✅ ' + name + ' 불러오기 완료: ' + appliedCount + '개 필드 적용';
            }
            alert(message);
            closeMappingManager();
        })
        .catch(function(e) {
            alert('매핑 로드 중 오류: ' + e.message);
        });
}

function deleteMappingByName(name) {
    if (!confirm('"' + name + '" 매핑 파일을 삭제하시겠습니까?')) {
        return;
    }
    
    fetch('/api/mappings/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (data.success) {
            alert('삭제 완료');
            showMappingManager();
        } else {
            alert('삭제 실패: ' + (data.error || '알 수 없는 오류'));
        }
    })
    .catch(function(e) {
        alert('삭제 중 오류: ' + e.message);
    });
}

function saveMappingWithName() {
    var name = document.getElementById('newMappingName').value.trim();
    if (!name) {
        alert('매핑 이름을 입력해주세요.');
        return;
    }
    
    if (Object.keys(columnMappings).length === 0) {
        alert('저장할 매핑이 없습니다.');
        return;
    }
    
    fetch('/api/mappings/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            mappings: columnMappings,
            name: name
        })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
        if (data.success) {
            alert('"' + name + '" 매핑이 저장되었습니다.');
            document.getElementById('newMappingName').value = '';
            showMappingManager();
        } else {
            alert('저장 실패: ' + (data.error || '알 수 없는 오류'));
        }
    })
    .catch(function(e) {
        alert('저장 중 오류: ' + e.message);
    });
}

document.addEventListener('DOMContentLoaded', function() {
    renderMetadataTree();
    
    document.getElementById('fileInput').addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            var file = e.target.files[0];
            var formData = new FormData();
            formData.append('file', file);
            
            fetch('/api/batch/upload', {
                method: 'POST',
                body: formData
            })
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.error) {
                    alert(data.error);
                    return;
                }
                
                uploadedData = data;
                columnMappings = {};
                fieldOrder = [];
                document.getElementById('fileDetails').textContent = '파일명: ' + data.filename + ', 행: ' + data.rows + ', 열: ' + data.columns.length;
                document.getElementById('fileInfo').classList.remove('hidden');
                
                renderDataColumns();
                
                setTimeout(function() { showStep(2); }, 1000);
            })
            .catch(function(error) {
                console.error('파일 업로드 오류:', error);
                alert('파일 업로드 중 오류가 발생했습니다.');
            });
        }
    });
    
    document.getElementById('nextBtn').addEventListener('click', nextStep);
    document.getElementById('prevBtn').addEventListener('click', prevStep);
    
});