from flask import Flask, render_template, request, redirect, url_for, session
import rdflib
from datetime import datetime

app = Flask(__name__, template_folder='templates')
app.secret_key = 'super_secret_key_for_weekend_events'


graph = rdflib.Graph()
graph.parse("event50.ttl", format="turtle")

NS = "http://www.semanticweb.org/ontologies/2023/weekend_events#"
namespaces = {"ev": NS}
EX = rdflib.Namespace(NS)


def clean_uri_list(uri_string):
    if not uri_string or uri_string == 'None': return []
    return [item.strip().split('#')[-1] for item in str(uri_string).split(',')]


def get_raw_data():
    query = f"""
        PREFIX ev: <{NS}>
        SELECT ?m ?name ?desc ?cost ?animals 
               (GROUP_CONCAT(DISTINCT ?season; separator=", ") AS ?seasons)
               (GROUP_CONCAT(DISTINCT ?company; separator=", ") AS ?companies)
               (GROUP_CONCAT(DISTINCT ?fmt; separator=", ") AS ?fmts)
               (GROUP_CONCAT(DISTINCT ?loc; separator=", ") AS ?locs)
               (GROUP_CONCAT(DISTINCT ?discount; separator=", ") AS ?discounts)
        WHERE {{
            ?m a ev:Мероприятие ;
               ev:название ?name ;
               ev:стоимость ?cost ;
               ev:сезон ?season ;
               ev:подходитДля ?company ;
               ev:можно_с_животными ?animals .
            OPTIONAL {{ ?m ev:описание ?desc }}
            ?m ev:имеетФормат ?fmt .
            ?m ev:проходитВ ?loc .
            OPTIONAL {{
                ?m ev:имеетСкидку ?d .
                ?d ev:размер_скидки_процент ?discount .
            }}
        }}
        GROUP BY ?m ?name ?desc ?cost ?animals
        ORDER BY ?name
    """
    out = []
    for row in graph.query(query, initNs=namespaces):
        discounts = [int(float(d)) for d in str(row.discounts).split(', ') if
                     d and d != 'None'] if row.discounts else []
        best_discount = max(discounts) if discounts else 0


        event_id = str(row.m).split('#')[-1]

        out.append({
            "id": event_id,
            "name": str(row.name),
            "desc": str(row.desc) if row.desc and str(row.desc) != 'None' else "",
            "cost": float(row.cost),
            "season": ", ".join(clean_uri_list(row.seasons)),
            "company": ", ".join(clean_uri_list(row.companies)),
            "seasons_list": clean_uri_list(row.seasons),
            "companies_list": clean_uri_list(row.companies),
            "animals": str(row.animals).lower() == 'true',
            "fmts_list": clean_uri_list(row.fmts),
            "locs_list": clean_uri_list(row.locs),
            "fmt": ", ".join(clean_uri_list(row.fmts)),
            "loc": ", ".join(clean_uri_list(row.locs)),
            "discount": best_discount
        })
    return out


def get_all_unique_formats():
    query = f"PREFIX ev: <{NS}> SELECT ?name WHERE {{ ?d a ev:Формат . BIND(REPLACE(STR(?d), \".*#\", \"\") AS ?name) }}"
    return sorted([str(row.name) for row in graph.query(query, initNs=namespaces)])


def get_all_unique_locations():
    query = f"PREFIX ev: <{NS}> SELECT ?name WHERE {{ ?d a ev:Локация . BIND(REPLACE(STR(?d), \".*#\", \"\") AS ?name) }}"
    return sorted([str(row.name) for row in graph.query(query, initNs=namespaces)])


def get_all_discounts():
    query = f"PREFIX ev: <{NS}> SELECT ?name WHERE {{ ?d a ev:Скидка . BIND(REPLACE(STR(?d), \".*#\", \"\") AS ?name) }}"
    discounts = [str(row.name) for row in graph.query(query, initNs=namespaces)]
    return sorted(discounts) if discounts else ["Нет_скидки"]


@app.route('/admin_login', methods=['POST'])
def admin_login():
    password = request.form.get('password')
    if password == 'admin123':
        session['is_admin'] = True
        return {'status': 'ok'}
    return {'status': 'error', 'message': 'Неверный пароль'}, 401


@app.route('/admin_logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('events'))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/events', methods=['GET'])
@app.route('/<username>/users/', methods=['GET'])
def events(username=None):
    def events():
        events_list = get_raw_data()
        formats = get_all_unique_formats()
        locations = get_all_unique_locations()
        discounts = get_all_discounts()
        is_admin = session.get('is_admin', False)
        return render_template('events.html', events=events_list, formats=formats, locations=locations, discounts=discounts,
                               is_admin=is_admin)


@app.route('/add_event', methods=['POST'])
def add_event():
    if not session.get('is_admin'): return "Доступ запрещен", 403

    name = request.form.get('name', '').strip()
    if not name: return "Ошибка: Название обязательно", 400

    new_id = f"Мероприятие_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    event_uri = EX[new_id]

    save_event_data(event_uri, request.form)
    graph.serialize(destination="event50.ttl", format="turtle")
    return redirect(url_for('events'))


@app.route('/edit_event/<event_id>', methods=['POST'])
def edit_event(event_id):
    if not session.get('is_admin'): return "Доступ запрещен", 403

    event_uri = EX[event_id]
    for p, o in graph.predicate_objects(event_uri):
        if p != rdflib.RDF.type:
            graph.remove((event_uri, p, o))

    save_event_data(event_uri, request.form)
    graph.serialize(destination="event50.ttl", format="turtle")
    return redirect(url_for('events'))


@app.route('/delete_event/<event_id>', methods=['POST'])
def delete_event(event_id):
    if not session.get('is_admin'): return "Доступ запрещен", 403
    event_uri = EX[event_id]
    graph.remove((event_uri, None, None))
    graph.serialize(destination="event50.ttl", format="turtle")
    return redirect(url_for('events'))


def save_event_data(event_uri, form):
    name = form.get('name', '').strip()
    desc = form.get('desc', '').strip()
    cost = form.get('cost', '0').strip()
    animals = form.get('animals') == 'on'

    seasons = form.getlist('season')
    companies = form.getlist('company')
    discounts = form.getlist('discount')
    formats = form.getlist('formats')
    locations = form.getlist('locations')

    graph.add((event_uri, rdflib.RDF.type, EX.Мероприятие))
    graph.add((event_uri, EX.название, rdflib.Literal(name)))
    if desc: graph.add((event_uri, EX.описание, rdflib.Literal(desc)))

    try:
        cost_float = float(cost)
    except ValueError:
        cost_float = 0.0
    graph.add((event_uri, EX.стоимость, rdflib.Literal(cost_float, datatype=rdflib.XSD.float)))
    graph.add((event_uri, EX.можно_с_животными, rdflib.Literal(animals, datatype=rdflib.XSD.boolean)))

    if seasons:
        for s in seasons: graph.add((event_uri, EX.сезон, rdflib.Literal(s)))
    else:
        graph.add((event_uri, EX.сезон, rdflib.Literal("Всесезон")))

    if companies:
        for c in companies: graph.add((event_uri, EX.подходитДля, rdflib.Literal(c)))
    else:
        graph.add((event_uri, EX.подходитДля, rdflib.Literal("Один")))

    if discounts:
        for d in discounts: graph.add((event_uri, EX.имеетСкидку, EX[d]))
    else:
        graph.add((event_uri, EX.имеетСкидку, EX['Нет_скидки']))

    for fmt in formats:
        if fmt.strip():
            fmt_uri = EX[fmt.strip()]
            graph.add((event_uri, EX.имеетФормат, fmt_uri))
            graph.add((fmt_uri, rdflib.RDF.type, EX.Формат))

    for loc in locations:
        if loc.strip():
            loc_uri = EX[loc.strip()]
            graph.add((event_uri, EX.проходитВ, loc_uri))
            graph.add((loc_uri, rdflib.RDF.type, EX.Локация))



@app.route('/recommendations', methods=['GET', 'POST'])
def recommendations():
    recs = []
    filter_string = ""
    all_events = get_raw_data()
    formats = get_all_unique_formats()
    locations = get_all_unique_locations()

    if request.method == 'POST':
        seasons = request.form.getlist('season')
        companies = request.form.getlist('company')
        selected_formats = request.form.getlist('format')
        selected_locations = request.form.getlist('location')
        max_price = request.form.get('max_price', '').strip()
        with_animals = request.form.get('with_animals') == 'on'

        active_filters = []
        if seasons: active_filters.append(f"Сезон: {', '.join(seasons)}")
        if companies: active_filters.append(f"Компания: {', '.join(companies)}")
        if max_price: active_filters.append(f"Бюджет до: {max_price} ₽")
        if selected_formats: active_filters.append(f"Формат: {', '.join(selected_formats)}")
        if selected_locations: active_filters.append(f"Локация: {', '.join(selected_locations)}")
        if with_animals: active_filters.append("Можно с животными")

        filter_string = " | ".join(active_filters) if active_filters else "Без фильтров (показаны все)"

        if max_price:
            try:
                max_price = float(max_price)
            except ValueError:
                max_price = None

        for e in all_events:
            score = 0
            matches = []

            if seasons:
                if any(s in e['seasons_list'] for s in seasons) or "Всесезон" in e['seasons_list']:
                    score += 30
                    matches.append("сезон")

            if companies:
                if any(c in e['companies_list'] for c in companies):
                    score += 30
                    matches.append("компания")

            if max_price is not None:
                if e['cost'] <= max_price:
                    score += 20
                    matches.append("цена")

            if selected_formats:
                if any(f in e['fmts_list'] for f in selected_formats):
                    score += 40
                    matches.append("формат")

            if selected_locations:
                if any(l in e['locs_list'] for l in selected_locations):
                    score += 40
                    matches.append("локация")

            if with_animals:
                if e['animals']:
                    score += 10
                    matches.append("животные")

            if not active_filters:
                score = 100

            if score > 0:
                final_price = e['cost'] - (e['cost'] * e['discount'] / 100)
                e['final_price'] = round(final_price, 2)
                e['score'] = score
                e['matches'] = ", ".join(matches)
                recs.append(e)

        recs.sort(key=lambda x: x["score"], reverse=True)

    return render_template('recommendations.html', recs=recs, formats=formats, locations=locations,
                           filter_string=filter_string)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=60080, debug=True)