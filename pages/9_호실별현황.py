import streamlit as st
import db
import sidebar
import views

user = sidebar.page_setup("호실별 현황", "🔍")

site_id, site, _ = sidebar.select_site(user)

c1, c2 = st.columns(2)
bld_id, _ = sidebar.select_building(site_id, container=c1)
units = db.get_units(site_id=site_id, building_id=bld_id)
if not units:
    c2.warning("호실이 없습니다.")
    st.stop()
unit = sidebar.select_unit(units, container=c2)

st.divider()
views.render_unit_detail(unit)
