"""Automatic provenance-rich PDF; computed indicators, never forest-loss claims."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,PageBreak,KeepTogether

GREEN=colors.HexColor('#123f38')
MUTED=colors.HexColor('#5d746c')
PAPER=colors.HexColor('#eff5f0')


def make_pdf(result,directory):
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleFP',fontName='Helvetica-Bold',fontSize=25,leading=30,textColor=GREEN,spaceAfter=12))
    styles.add(ParagraphStyle(name='HeadingFP',fontName='Helvetica-Bold',fontSize=13,leading=18,textColor=GREEN,spaceBefore=12,spaceAfter=8))
    styles.add(ParagraphStyle(name='BodyFP',fontSize=9,leading=13,textColor=GREEN,spaceAfter=6))
    styles.add(ParagraphStyle(name='SmallFP',fontSize=7.5,leading=10,textColor=MUTED,spaceAfter=4))
    def text(value):
        return escape(str(value).replace('·',' / ').replace('–','-').replace('—','-'))
    def p(value,style='BodyFP'):
        return Paragraph(text(value),styles[style])
    def heading(value):
        return p(value,'HeadingFP')
    width=A4[0]-80
    label='SIMULATED DATA - NO OBSERVED ENVIRONMENTAL CHANGE' if result['is_simulated'] else 'TECHNICAL INDICATORS - NO CONFIRMED FOREST LOSS'
    story=[p('ForestPulse','SmallFP'),p('Image comparison report','TitleFP'),p(label,'HeadingFP'),p(result['interpretation']),
        p('Generated UTC: '+result['created_at_utc']+' / Comparison: '+result['id'],'SmallFP'),Spacer(1,8)]
    def meta(entry):
        date=('Scenario date (not acquisition): '+str(entry.get('scenario_date'))) if entry['is_simulated'] else 'Acquisition date: '+str(entry.get('acquisition_date') or 'Unknown')
        rows=[p(entry['name'],'HeadingFP'),p(date),p(entry['filename'],'SmallFP'),p('Source: '+entry['source'],'SmallFP'),
                p('Sensor: '+entry['sensor'],'SmallFP'),p('Type / units: '+entry['data_type']+' / '+entry['units'],'SmallFP')]
        if entry.get('frequency'):
            rows.append(p('Frequency / polarization: '+entry['frequency']+' / '+entry['polarization'],'SmallFP'))
        variable=(entry.get('provenance') or {}).get('variable')
        if variable: rows.append(p('Radar variable: '+variable,'SmallFP'))
        return rows
    metadata=Table([[meta(result['before']),meta(result['after'])]],colWidths=[width/2,width/2])
    metadata.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,-1),PAPER),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#d6e4db')),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10)]))
    story.extend([metadata,Spacer(1,10),p('Area: '+result['before']['area']),heading('Computed comparison summary')])
    s=result['summary']
    summary=Table([[p('Shared valid pixels','SmallFP'),p('Flagged pixels','SmallFP'),p('Flagged share','SmallFP'),p('Regions','SmallFP')],
        [p(f'{s["valid_pixels"]:,}'),p(f'{s["changed_pixels"]:,}'),p(f'{s["changed_percent_of_valid"]:.2f}%'),p(s['region_count'])]],colWidths=[width/4]*4)
    summary.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PAPER),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.extend([summary,heading('Aligned baseline and follow-up')])
    def picture(name):
        return Image(str(directory/(name+'.png')),width=(width-12)/2,height=(width-12)/2*result['height']/result['width'])
    photos=Table([[picture('before'),picture('after')],[p('Baseline - aligned valid comparison footprint','SmallFP'),p('Follow-up - aligned to baseline','SmallFP')]],colWidths=[width/2]*2)
    photos.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),6)]))
    story.extend([photos,p('Display stretches do not modify the quantitative radar values. Dark borders mark invalid or non-overlapping pixels.','SmallFP'),
        p('No hectare estimate or confirmed mangrove-loss measurement is produced.','SmallFP'),PageBreak(),
        p(label,'SmallFP'),heading('Change magnitude and highlighted regions')])
    maps=Table([[picture('heatmap'),picture('overlay')],[p('Heatmap: dark = low; yellow = higher magnitude','SmallFP'),p('Overlay: coral = flagged; pale outlines = regions','SmallFP')]],colWidths=[width/2]*2)
    maps.setStyle(TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),6),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.extend([maps,p(f'Heatmap scale: 0 to {result["heatmap_scale_max"]:.3f} {s["indicator_units"]}.','SmallFP'),heading('Method and settings'),
        p(result['method']),p(f'Threshold: {result["parameters"]["threshold"]} {s["indicator_units"]}; filter: {result["parameters"]["filter"]}, radius {result["parameters"]["noise_radius"]}; minimum region: {result["parameters"]["min_region_pixels"]} pixels.'),
        p('Alignment: '+result['alignment']['method']),p(result['alignment']['confidence_note'],'SmallFP')])
    a=result['alignment']
    if a.get('matches') is not None:
        story.append(p(f'Measured feature matches: {a["matches"]}; RANSAC inliers: {a["inliers"]}; inlier ratio: {a["inlier_ratio"]:.3f}; residual RMSE: {a["reprojection_rmse_pixels"]:.3f} pixels. Confidence category: {a["confidence"]}.','SmallFP'))
    if a.get('crs'):
        story.append(p(f'Common grid: {a["crs"]}; resolution {a["resolution"]}; {result["width"]} x {result["height"]} pixels.','SmallFP'))
        story.append(p('Grid bounds (left, bottom, right, top): '+str(a['bounds'])+'. Shared valid comparison area is defined by the exported valid-pixel mask, not the entire rectangle.','SmallFP'))
    story.append(p(f'Mean absolute difference: {s["mean_absolute_difference"]:.4f}; 95th percentile: {s["p95_absolute_difference"]:.4f} {s["indicator_units"]}.','SmallFP'))
    story.append(heading('Detected image regions'))
    if result['regions']:
        rows=[[p(v,'SmallFP') for v in ['Region','Pixels','Mean magnitude','Indicator']]]
        for r in result['regions'][:8]:
            rows.append([p(str(r['id']),'SmallFP'),p(f'{r["pixels"]:,}','SmallFP'),p(f'{r["mean_indicator_magnitude"]:.3f}','SmallFP'),p(r['direction'],'SmallFP')])
        table=Table(rows,colWidths=[width*.15,width*.2,width*.25,width*.4],repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PAPER),('LINEBELOW',(0,0),(-1,0),.5,MUTED),('VALIGN',(0,0),(-1,-1),'TOP')]))
        story.append(table)
        story.append(p(f'Showing {min(8,len(result["regions"]))} largest regions of {s["region_count"]}. Outlines are image-space regions, not mapped forest boundaries.','SmallFP'))
    else:
        story.append(p('No regions exceeded the selected threshold and size filter. This is not evidence of no environmental change.'))
    story.append(heading('Interpretation and uncertainty'))
    story.extend(p('- '+warning,'SmallFP') for warning in result['warnings'])
    doc=SimpleDocTemplate(str(directory/'report.pdf'),pagesize=A4,rightMargin=40,leftMargin=40,topMargin=35,bottomMargin=40,
        title='ForestPulse - '+('SIMULATED ' if result['is_simulated'] else '')+'Image comparison',author='ForestPulse')
    def footer(canvas,_doc):
        canvas.setStrokeColor(colors.HexColor('#d6e4db'));canvas.line(40,30,A4[0]-40,30)
        canvas.setFont('Helvetica',7);canvas.setFillColor(MUTED)
        canvas.drawString(40,19,'ForestPulse | '+('SIMULATED' if result['is_simulated'] else 'TECHNICAL INDICATORS')+' | '+result['id'][:8])
        canvas.drawRightString(A4[0]-40,19,f'Page {_doc.page}')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
