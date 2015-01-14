window.ResourceCloud = angular.module('ResourceCloud', ['ngRoute', 'restangular', 'LocalStorageModule'])

.run(function($location, Restangular, AuthService) {
})

.config(function($routeProvider, RestangularProvider) {
    RestangularProvider.setBaseUrl('/api/v1');
})
