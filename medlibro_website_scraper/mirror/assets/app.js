/**
 * MedLibro Local Vue.js Application
 * Simplified version that works with local API and data
 */

// API Configuration
const API_BASE_URL = 'http://localhost:5000';

// Components (must be defined BEFORE routes that reference them)
const HomePage = {
    template: `
        <v-app>
            <v-main>
                <v-container>
                    <v-row justify="center">
                        <v-col cols="12" md="8">
                            <v-card class="pa-6">
                                <h1 class="text-h3 mb-4">MedLibro - Local Version</h1>
                                <p class="text-body-1 mb-4">
                                    Welcome to the local rebuild of MedLibro. This version uses your scraped data
                                    and serves it through a local API server.
                                </p>
                                <v-btn color="primary" to="/dashboard" large>
                                    Go to Dashboard
                                </v-btn>
                                <v-btn color="secondary" to="/revision" large class="ml-2">
                                    Start Revision
                                </v-btn>
                            </v-card>
                        </v-col>
                    </v-row>
                </v-container>
            </v-main>
        </v-app>
    `
};

const DashboardPage = {
    template: `
        <v-app>
            <app-bar></app-bar>
            <v-main>
                <v-container>
                    <h1 class="text-h4 mb-4">Dashboard</h1>
                    <v-row>
                        <v-col cols="12" md="6" v-for="year in years" :key="year.id">
                            <v-card>
                                <v-card-title>{{ year.label || year.id }}</v-card-title>
                                <v-card-actions>
                                    <v-btn text color="primary" @click="goToRevision(year.id)">
                                        Start Revision
                                    </v-btn>
                                </v-card-actions>
                            </v-card>
                        </v-col>
                    </v-row>
                </v-container>
            </v-main>
        </v-app>
    `,
    data() {
        return {
            years: []
        };
    },
    mounted() {
        this.loadYears();
    },
    methods: {
        async loadYears() {
            try {
                const response = await axios.get(`${API_BASE_URL}/api/v1/years`);
                this.years = response.data;
            } catch (error) {
                console.error('Failed to load years:', error);
            }
        },
        goToRevision(yearId) {
            this.$router.push({ path: '/revision', query: { year: yearId } });
        }
    }
};

const RevisionPage = {
    template: `
        <v-app>
            <app-bar></app-bar>
            <v-main>
                <v-container>
                    <h1 class="text-h4 mb-4">Revision</h1>
                    
                    <v-select
                        v-model="selectedYear"
                        :items="yearOptions"
                        label="Select Year"
                        @change="loadRevisionData"
                        class="mb-4"
                    ></v-select>
                    
                    <div v-if="loading">
                        <v-progress-circular indeterminate color="primary"></v-progress-circular>
                    </div>
                    
                    <div v-else-if="revisionData">
                        <v-card v-for="yearData in revisionData" :key="yearData.year" class="mb-4">
                            <v-card-title>{{ yearData.year_label || yearData.year }}</v-card-title>
                            <v-card-text>
                                <div v-for="theme in yearData.themes" :key="theme.id" class="mb-2">
                                    <h3>{{ theme.name }}</h3>
                                    <p>Chapters: {{ theme.chapters.join(', ') }}</p>
                                    <p>Questions: {{ theme.questions_count }}</p>
                                </div>
                            </v-card-text>
                        </v-card>
                    </div>
                </v-container>
            </v-main>
        </v-app>
    `,
    data() {
        return {
            selectedYear: null,
            yearOptions: [],
            revisionData: null,
            loading: false
        };
    },
    mounted() {
        this.loadYears();
        const yearParam = this.$route.query.year;
        if (yearParam) {
            this.selectedYear = yearParam;
            this.loadRevisionData();
        }
    },
    methods: {
        async loadYears() {
            try {
                const response = await axios.get(`${API_BASE_URL}/api/v1/years`);
                this.yearOptions = response.data.map(y => ({
                    value: y.id,
                    text: y.label || y.id
                }));
            } catch (error) {
                console.error('Failed to load years:', error);
            }
        },
        async loadRevisionData() {
            if (!this.selectedYear) return;
            
            this.loading = true;
            try {
                const response = await axios.get(`${API_BASE_URL}/api/v1/revision`);
                // Filter by selected year if needed
                this.revisionData = response.data.filter(d => d.year === this.selectedYear);
            } catch (error) {
                console.error('Failed to load revision data:', error);
            } finally {
                this.loading = false;
            }
        }
    }
};

const ExamPage = {
    template: `
        <v-app>
            <app-bar></app-bar>
            <v-main>
                <v-container>
                    <h1 class="text-h4">Exam Mode</h1>
                    <p>Exam functionality coming soon...</p>
                </v-container>
            </v-main>
        </v-app>
    `
};

const ProfilePage = {
    template: `
        <v-app>
            <app-bar></app-bar>
            <v-main>
                <v-container>
                    <h1 class="text-h4">Profile</h1>
                    <p>Profile page coming soon...</p>
                </v-container>
            </v-main>
        </v-app>
    `
};

const CoursesPage = {
    template: `<v-app><app-bar></app-bar><v-main><v-container><h1>Courses</h1></v-container></v-main></v-app>`
};

const PlaylistsPage = {
    template: `<v-app><app-bar></app-bar><v-main><v-container><h1>Playlists</h1></v-container></v-main></v-app>`
};

const SessionsPage = {
    template: `<v-app><app-bar></app-bar><v-main><v-container><h1>Sessions</h1></v-container></v-main></v-app>`
};

const PrioritizerPage = {
    template: `<v-app><app-bar></app-bar><v-main><v-container><h1>Prioritizer</h1></v-container></v-main></v-app>`
};

const PricingPage = {
    template: `<v-app><app-bar></app-bar><v-main><v-container><h1>Pricing</h1></v-container></v-main></v-app>`
};

const FAQPage = {
    template: `<v-app><app-bar></app-bar><v-main><v-container><h1>FAQ</h1></v-container></v-main></v-app>`
};

const NotFoundPage = {
    template: `
        <v-app>
            <app-bar></app-bar>
            <v-main>
                <v-container>
                    <h1 class="text-h4">404 - Page Not Found</h1>
                    <v-btn to="/" color="primary">Go Home</v-btn>
                </v-container>
            </v-main>
        </v-app>
    `
};

// App Bar Component
Vue.component('app-bar', {
    template: `
        <v-app-bar color="primary" dark>
            <v-app-bar-nav-icon @click="drawer = !drawer"></v-app-bar-nav-icon>
            <v-toolbar-title>MedLibro</v-toolbar-title>
            <v-spacer></v-spacer>
            <v-btn text to="/">Home</v-btn>
            <v-btn text to="/dashboard">Dashboard</v-btn>
            <v-btn text to="/revision">Revision</v-btn>
            <v-btn text to="/profile">Profile</v-btn>
        </v-app-bar>
    `,
    data() {
        return {
            drawer: false
        };
    }
});

// Vue Router (after all components are defined)
const routes = [
    { path: '/', component: HomePage },
    { path: '/dashboard', component: DashboardPage },
    { path: '/revision', component: RevisionPage },
    { path: '/exam', component: ExamPage },
    { path: '/profile', component: ProfilePage },
    { path: '/courses', component: CoursesPage },
    { path: '/playlists', component: PlaylistsPage },
    { path: '/sessions', component: SessionsPage },
    { path: '/prioritizer', component: PrioritizerPage },
    { path: '/pricing', component: PricingPage },
    { path: '/faq', component: FAQPage },
    { path: '*', component: NotFoundPage }
];

const router = new VueRouter({
    mode: 'history',
    routes: routes,
    base: '/'
});

// Vuex Store
const store = new Vuex.Store({
    state: {
        user: null,
        years: [],
        currentYear: null,
        questions: [],
        loading: false
    },
    mutations: {
        SET_USER(state, user) { state.user = user; },
        SET_YEARS(state, years) { state.years = years; },
        SET_CURRENT_YEAR(state, year) { state.currentYear = year; },
        SET_QUESTIONS(state, questions) { state.questions = questions; },
        SET_LOADING(state, loading) { state.loading = loading; }
    },
    actions: {
        async loadYears({ commit }) {
            try {
                const response = await axios.get(API_BASE_URL + '/api/v1/years');
                commit('SET_YEARS', response.data);
            } catch (error) {
                console.error('Failed to load years:', error);
            }
        }
    }
});

// Initialize Vue App
new Vue({
    router: router,
    store: store,
    vuetify: new Vuetify({ theme: { dark: false } })
}).$mount('#app');
