from datetime import datetime,timezone
import streamlit as st
import pandas as pd
from src.config import ADMIN_PASSWORD,APP_ENV
from src.db import *
from src.data import case_bank
from src.ui import *
from src.analytics import *
st.set_page_config(page_title='AI-RETINA Human–AI Platform',page_icon='👁️',layout='wide');init_db();inject_css();CASES=case_bank()
st.title('AI-RETINA Human–AI Learning & Decision Platform');st.caption(f'Online edition · Research · Live · Learning · Admin · {APP_ENV}')
mode=st.sidebar.radio('Platform mode',['Research Study','Live Conference','Self-Learning','Investigator / Admin'])
if mode=='Research Study':
    st.header('Research Study')
    if 'research_uid' not in st.session_state:
        with st.form('research_profile'):
            years=st.number_input('Years in ophthalmology',0,60,5);spec=st.selectbox('Clinical profile',['Retina specialist','General ophthalmologist','Resident/Fellow','Other']);freq=st.selectbox('OCT reading frequency',['Daily','Several times/week','Weekly','Less than weekly']);study=st.selectbox('Case set',['RANDOM10','ALL','nAMD','RVO','DME','PCV']);go=st.form_submit_button('Start research',type='primary')
        if go:
            uid=create_user('research',years,spec,freq);assign_cases(uid,CASES,study);st.session_state.research_uid=uid;st.session_state.research_started=datetime.now(timezone.utc);st.rerun()
    else:
        uid=st.session_state.research_uid;row,seq=next_research_case(uid,CASES);st.success(f'Anonymous research code: **{uid}**')
        if row is None:st.success('Research case set completed.')
        else:
            st.subheader(f'Blinded Retina Case · {seq}');show_case(row,True)
            with st.form(f'research_{row.case_id}'):
                diag=st.radio('Diagnosis',DIAGNOSES,index=None,horizontal=True);bio={b:st.radio(b,['Absent','Present'],horizontal=True,key=f'r_{row.case_id}_{b}') for b in BIOMARKERS};mgmt=st.radio('Management',MANAGEMENT,index=None,horizontal=True);cf=st.select_slider('Confidence',CONF,value=3);go=st.form_submit_button('Submit & next',type='primary')
            if go:
                if diag is None or mgmt is None:st.error('Complete diagnosis and management.')
                else:
                    sec=(datetime.now(timezone.utc)-st.session_state.research_started).total_seconds();save_research(uid,row,diag,mgmt,cf,bio,sec);st.session_state.research_started=datetime.now(timezone.utc);st.rerun()
elif mode=='Live Conference':
    st.header('Live Conference')
    if 'live_code' not in st.session_state:st.session_state.live_code=new_code('LIVE')
    code=st.session_state.live_code;st.success(f'Participant Code: **{code}**')
    @st.fragment(run_every='2s')
    def live_status():
        sess=get_live_session();st.caption(('Waiting for moderator' if not sess['active_case_id'] else ('VOTING OPEN' if sess['voting_open'] else ('RESULTS REVEALED' if sess['reveal_results'] else 'CASE OPEN')))+' · auto-refresh 2 s')
    live_status();sess=get_live_session()
    if not sess['active_case_id']:st.info('Moderator has not opened a case yet.')
    else:
        row=CASES[CASES.case_id==sess['active_case_id']].iloc[0];show_case(row,True);existing=get_live_vote(code,row.case_id)
        if sess['voting_open']:
            with st.form(f'live_{row.case_id}'):
                diag=st.radio('Diagnosis',DIAGNOSES,index=(DIAGNOSES.index(existing['diagnosis']) if existing and existing['diagnosis'] in DIAGNOSES else None),horizontal=True);mgmt=st.radio('Management',MANAGEMENT,index=(MANAGEMENT.index(existing['management']) if existing and existing['management'] in MANAGEMENT else None),horizontal=True);cf=st.select_slider('Confidence',CONF,value=(int(existing['confidence']) if existing else 3));go=st.form_submit_button('Submit / update live vote',type='primary')
            if go:
                if diag is None or mgmt is None:st.error('Complete diagnosis and management.')
                else:save_live_vote(code,row.case_id,diag,mgmt,cf);st.success('Vote recorded.');st.rerun()
        else:st.warning('Voting is closed.')
        if sess['reveal_results']:
            V=frames()['live'];v=V[V.case_id==row.case_id];st.subheader('Live results');st.metric('Votes',len(v));
            if not v.empty:st.bar_chart(v.management.value_counts())
            st.write(f'Expert: **{row.expert_management}** · TIDE: **{row.tide_management}**')
elif mode=='Self-Learning':
    st.header('Self-Learning')
    if 'learning_uid' not in st.session_state:
        with st.form('learning_profile'):
            years=st.number_input('Years in ophthalmology',0,60,2,key='ly');spec=st.selectbox('Level',['Resident/Fellow','General ophthalmologist','Retina trainee','Retina specialist']);freq=st.selectbox('OCT reading frequency',['Daily','Several times/week','Weekly','Less than weekly'],key='lf');go=st.form_submit_button('Start learning',type='primary')
        if go:st.session_state.learning_uid=create_user('learning',years,spec,freq);st.session_state.learning_index=0;st.session_state.learning_stage='human';st.rerun()
    else:
        uid=st.session_state.learning_uid;i=st.session_state.learning_index%len(CASES);row=CASES.iloc[i];st.success(f'Learner code: **{uid}**');show_case(row,True);stage=st.session_state.learning_stage
        if stage=='human':
            with st.form(f'learn_h_{row.case_id}'):
                diag=st.radio('Diagnosis',DIAGNOSES,index=None,horizontal=True);bio={b:st.radio(b,['Absent','Present'],horizontal=True,key=f'lh_{row.case_id}_{b}') for b in BIOMARKERS};mgmt=st.radio('Management',MANAGEMENT,index=None,horizontal=True);cf=st.select_slider('Confidence',CONF,value=3);go=st.form_submit_button('Commit human answer',type='primary')
            if go and diag and mgmt:save_learning(uid,row,1,'human',diag,mgmt,cf,bio);st.session_state.learning_stage='ai';st.rerun()
        elif stage=='ai':
            st.markdown(f"<div class='ai'><b>TIDE AI</b><br>Diagnosis: <b>{row.tide_diagnosis}</b><br>Management: <b>{row.tide_management}</b><br>IRF {row.tide_irf} · SRF {row.tide_srf} · PED {row.tide_ped} · SHRM {row.tide_shrm} · HRF {row.tide_hrf}</div>",unsafe_allow_html=True)
            if st.button('Continue to expert reference',type='primary'):st.session_state.learning_stage='expert';st.rerun()
        else:
            st.markdown(f"<div class='expert'><b>Expert reference</b><br>Diagnosis: <b>{row.expert_diagnosis}</b><br>Management: <b>{row.expert_management}</b><br>IRF {row.irf_current} · SRF {row.srf_current} · PED {row.ped_current} · SHRM {row.shrm_current} · HRF {row.hrf_current}</div>",unsafe_allow_html=True)
            if st.button('Next case',type='primary'):st.session_state.learning_index+=1;st.session_state.learning_stage='human';st.rerun()
else:
    st.header('Investigator / Admin');pw=st.text_input('Admin password',type='password')
    if pw!=ADMIN_PASSWORD:st.info('Enter admin password.');st.stop()
    F=frames();U,R,L,V=F['users'],F['research'],F['learning'],F['live'];t1,t2,t3,t4=st.tabs(['Research analytics','Human–AI safety','Learning analytics','Live moderator'])
    with t1:
        a,b,c=st.columns(3);a.metric('Research doctors',int((U.role=='research').sum()) if len(U) else 0);b.metric('Research responses',len(R));c.metric('Fleiss κ','—' if R.empty else f'{fleiss_kappa(R):.3f}')
        if not R.empty:
            st.dataframe(disagreement_table(R),width='stretch',hide_index=True);joined=R.merge(U[['user_id','specialty','years_experience']],on='user_id',how='left').merge(CASES[['case_id','disease_module','expert_management']],on='case_id',how='left');joined['expert_concordance']=joined.management==joined.expert_management;st.dataframe(joined.groupby('specialty').agg(n=('user_id','nunique'),responses=('case_id','count'),expert_concordance=('expert_concordance','mean'),confidence=('confidence','mean')).reset_index(),width='stretch',hide_index=True);st.download_button('Download research CSV',joined.to_csv(index=False).encode('utf-8-sig'),'research_analysis.csv','text/csv')
    with t2:
        S=human_ai_safety(R,CASES)
        if S.empty:st.info('No research responses.')
        else:
            st.dataframe(S.safety_class.value_counts().rename_axis('class').reset_index(name='n'),width='stretch',hide_index=True);x,y,z=st.columns(3);x.metric('Silent failure',f"{100*(S.safety_class=='Silent failure: Human + AI wrong').mean():.1f}%");y.metric('Human override needed',f"{100*(S.safety_class=='Human override needed').mean():.1f}%");z.metric('AI rescue opportunity',f"{100*(S.safety_class=='AI rescue opportunity').mean():.1f}%")
    with t3:
        if L.empty:st.info('No learning attempts.')
        else:
            H=L[L.stage=='human'].merge(CASES[['case_id','expert_management','expert_diagnosis']+[b.lower()+'_current' for b in BIOMARKERS]],on='case_id',how='left');H['management_correct']=H.management==H.expert_management;H['diagnosis_correct']=H.diagnosis==H.expert_diagnosis
            for b in BIOMARKERS:H[b+'_correct']=H[b.lower()].astype(str).str.lower()==H[b.lower()+'_current'].astype(str).str.lower()
            st.dataframe(H.groupby('user_id')[['management_correct','diagnosis_correct']+[b+'_correct' for b in BIOMARKERS]].mean().reset_index(),width='stretch',hide_index=True)
    with t4:
        sess=get_live_session();ids=CASES.case_id.tolist();sel=st.selectbox('Select case',ids,index=ids.index(sess['active_case_id']) if sess['active_case_id'] in ids else 0);preview=CASES[CASES.case_id==sel].iloc[0];c1,c2,c3,c4=st.columns(4)
        if c1.button('1 · Open case',type='primary'):update_live(active_case_id=sel,voting_open=False,reveal_results=False);st.rerun()
        if c2.button('2 · Open voting'):update_live(voting_open=True,reveal_results=False);st.rerun()
        if c3.button('3 · Close voting'):update_live(voting_open=False,reveal_results=False);st.rerun()
        if c4.button('4 · Reveal results'):update_live(voting_open=False,reveal_results=True);st.rerun()
        if sess['active_case_id']:st.metric('Votes received',live_vote_count(sess['active_case_id']))
        st.subheader('Case Preview');show_case(preview,False)
