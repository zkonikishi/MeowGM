const exportSection=document.createElement('section');
exportSection.innerHTML=`<h2>生成待发布文件</h2><p>先保存草稿，再生成供官网发布的内容文件。生成成功后仍需提交官网，公告不会自动上线。</p>
<label>已有官网公告文件（可选）<input id="content-base" type="file" accept=".json,application/json"></label>
<label>修改理由<input id="content-reason" maxlength="500"></label>
<label>拟发布时间（本地时间）<input id="content-planned" type="datetime-local"></label>
<button id="content-export">生成待发布文件</button><p id="content-result" role="status"></p>`;
$('workspace').append(exportSection);
$('content-export').onclick=()=>run(async()=>{const planned=new Date($('content-planned').value);if(!Number.isFinite(planned.valueOf()))throw Error('请选择拟发布时间');const file=$('content-base').files[0];if(file&&file.size>524288)throw Error('官网内容文件超过512KB');const body={reason:$('content-reason').value,plannedAt:planned.toISOString()};if(file)body.baseRaw=await file.text();const data=await api('/api/admin/content/export',body);$('content-result').textContent=data.message+'\n内容文件：'+data.contentPath+'\n审核清单：'+data.handoffPath+'\nSHA256：'+data.sha256;});
