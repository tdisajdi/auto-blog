<?php
/**
 * Plugin Name: ondo Polylang REST
 * Description: Polylang(무료판)의 글 언어 지정·번역 연결을 REST API로 여는 작은 전용 플러그인. ondo 자동 발행용.
 * Version: 1.4.3
 * Author: ondo
 * License: GPL-2.0-or-later
 * Requires PHP: 7.4
 *
 * 하는 일(이 셋뿐):
 *   GET  /ondo/v1/languages            - 사이트 언어 목록
 *   GET  /ondo/v1/lang/<id>            - 글(페이지)의 언어와 번역 연결 읽기
 *   POST /ondo/v1/lang/<id>  {lang}    - 글 언어 지정
 *   POST /ondo/v1/link {translations:{ko:1,en:2}} - 번역 연결 후 실제로 연결됐는지 다시 읽어 돌려줌
 *   GET  /ondo/v1/unassigned/<post|page> - 언어가 안 정해진 글 목록
 *   GET/POST /ondo/v1/term-lang/<id> {lang} - 분류(카테고리) 언어 읽기·지정
 *   POST /ondo/v1/term-link {translations:{ko:3,en:9}} - 분류 번역 연결
 *   (화면) 모든 페이지 <head>에 window.ondoLang = [{slug,url,current,missing}] - 머리글 국기 버튼이 씀
 *   (화면) /<IndexNow 키>.txt - IndexNow 키를 글자로(1.4.0, 11-22: 빙 등 검색엔진에 새 글 알림 - 키는 공개 값)
 * 권한: 해당 글을 고칠 수 있는 로그인 사용자만(분류는 분류 관리 권한).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function ondo_pll_ready() {
	return function_exists( 'pll_set_post_language' ) && function_exists( 'pll_save_post_translations' )
		&& function_exists( 'pll_get_post_language' ) && function_exists( 'pll_get_post_translations' )
		&& function_exists( 'pll_languages_list' );
}

function ondo_pll_missing() {
	return new WP_Error( 'ondo_no_polylang', 'Polylang이 켜져 있지 않습니다.', array( 'status' => 503 ) );
}

function ondo_pll_state( $id ) {
	$id = (int) $id;
	return array(
		'id'           => $id,
		'type'         => get_post_type( $id ),
		'status'       => get_post_status( $id ),
		'lang'         => pll_get_post_language( $id, 'slug' ) ?: null,
		'translations' => (object) pll_get_post_translations( $id ),
	);
}

function ondo_pll_can_edit( $request ) {
	$id = (int) $request['id'];
	return $id > 0 && get_post( $id ) && current_user_can( 'edit_post', $id );
}

add_action( 'rest_api_init', function () {
	register_rest_route( 'ondo/v1', '/languages', array(
		'methods'             => 'GET',
		'permission_callback' => function () { return current_user_can( 'edit_posts' ); },
		'callback'            => function () {
			if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
			return array( 'languages' => pll_languages_list( array( 'fields' => 'slug' ) ), 'default' => function_exists( 'pll_default_language' ) ? pll_default_language() : null );
		},
	) );

	register_rest_route( 'ondo/v1', '/lang/(?P<id>\d+)', array(
		array(
			'methods'             => 'GET',
			'permission_callback' => 'ondo_pll_can_edit',
			'callback'            => function ( $request ) {
				if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
				return ondo_pll_state( $request['id'] );
			},
		),
		array(
			'methods'             => 'POST',
			'permission_callback' => 'ondo_pll_can_edit',
			'args'                => array( 'lang' => array( 'required' => true, 'type' => 'string' ) ),
			'callback'            => function ( $request ) {
				if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
				$lang = sanitize_key( $request['lang'] );
				if ( ! in_array( $lang, pll_languages_list( array( 'fields' => 'slug' ) ), true ) ) {
					return new WP_Error( 'ondo_bad_lang', '사이트에 없는 언어입니다: ' . $lang, array( 'status' => 400 ) );
				}
				pll_set_post_language( (int) $request['id'], $lang );
				clean_post_cache( (int) $request['id'] );
				return ondo_pll_state( $request['id'] );
			},
		),
	) );

	register_rest_route( 'ondo/v1', '/link', array(
		'methods'             => 'POST',
		'permission_callback' => function () { return current_user_can( 'edit_posts' ); },
		'args'                => array( 'translations' => array( 'required' => true ) ),
		'callback'            => function ( $request ) {
			if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
			$langs = pll_languages_list( array( 'fields' => 'slug' ) );
			$pairs = array();
			foreach ( (array) $request['translations'] as $lang => $id ) {
				$lang = sanitize_key( $lang );
				$id   = (int) $id;
				if ( ! in_array( $lang, $langs, true ) || ! get_post( $id ) || ! current_user_can( 'edit_post', $id ) ) {
					return new WP_Error( 'ondo_bad_pair', '연결할 수 없는 짝: ' . $lang . '=' . $id, array( 'status' => 400 ) );
				}
				if ( pll_get_post_language( $id, 'slug' ) !== $lang ) {
					pll_set_post_language( $id, $lang );   // 연결 전에 각 글 언어를 먼저 맞춤(순서가 틀리면 연결이 조용히 안 됨)
				}
				$pairs[ $lang ] = $id;
			}
			if ( count( $pairs ) < 2 ) {
				return new WP_Error( 'ondo_need_two', '두 언어 이상이 필요합니다.', array( 'status' => 400 ) );
			}
			pll_save_post_translations( $pairs );
			$out = array();
			foreach ( $pairs as $lang => $id ) {
				clean_post_cache( $id );
				$out[] = ondo_pll_state( $id );
			}
			$ok = true;
			foreach ( $out as $st ) {
				foreach ( $pairs as $lang => $id ) {
					$t = (array) $st['translations'];
					if ( ! isset( $t[ $lang ] ) || (int) $t[ $lang ] !== $id ) { $ok = false; }
				}
			}
			return array( 'linked' => $ok, 'posts' => $out );
		},
	) );

	register_rest_route( 'ondo/v1', '/unassigned/(?P<type>post|page)', array(
		'methods'             => 'GET',
		'permission_callback' => function () { return current_user_can( 'edit_posts' ); },
		'callback'            => function ( $request ) {
			if ( ! ondo_pll_ready() ) { return ondo_pll_missing(); }
			$type = in_array( $request['type'], array( 'post', 'page' ), true ) ? $request['type'] : 'page';
			$ids  = get_posts( array( 'post_type' => $type, 'post_status' => array( 'publish', 'draft', 'private', 'pending' ), 'numberposts' => 200, 'fields' => 'ids', 'lang' => '' ) );
			$none = array();
			foreach ( $ids as $id ) {
				if ( ! pll_get_post_language( $id, 'slug' ) ) { $none[] = (int) $id; }
			}
			return array( 'type' => $type, 'checked' => count( $ids ), 'no_language' => $none );
		},
	) );
} );

function ondo_term_state( $id ) {
	$id = (int) $id;
	return array(
		'id'           => $id,
		'lang'         => pll_get_term_language( $id, 'slug' ) ?: null,
		'translations' => (object) pll_get_term_translations( $id ),
	);
}

function ondo_terms_ready() {
	return function_exists( 'pll_set_term_language' ) && function_exists( 'pll_save_term_translations' )
		&& function_exists( 'pll_get_term_language' ) && function_exists( 'pll_get_term_translations' );
}

add_action( 'rest_api_init', function () {
	$can = function () { return current_user_can( 'manage_categories' ); };
	register_rest_route( 'ondo/v1', '/term-lang/(?P<id>\d+)', array(
		array(
			'methods' => 'GET', 'permission_callback' => $can,
			'callback' => function ( $request ) {
				if ( ! ondo_terms_ready() ) { return ondo_pll_missing(); }
				return ondo_term_state( $request['id'] );
			},
		),
		array(
			'methods' => 'POST', 'permission_callback' => $can,
			'args' => array( 'lang' => array( 'required' => true, 'type' => 'string' ) ),
			'callback' => function ( $request ) {
				if ( ! ondo_terms_ready() ) { return ondo_pll_missing(); }
				$lang = sanitize_key( $request['lang'] );
				if ( ! get_term( (int) $request['id'] ) || ! in_array( $lang, pll_languages_list( array( 'fields' => 'slug' ) ), true ) ) {
					return new WP_Error( 'ondo_bad_term', '분류나 언어가 없습니다.', array( 'status' => 400 ) );
				}
				pll_set_term_language( (int) $request['id'], $lang );
				return ondo_term_state( $request['id'] );
			},
		),
	) );
	register_rest_route( 'ondo/v1', '/term-link', array(
		'methods' => 'POST', 'permission_callback' => $can,
		'args' => array( 'translations' => array( 'required' => true ) ),
		'callback' => function ( $request ) {
			if ( ! ondo_terms_ready() ) { return ondo_pll_missing(); }
			$langs = pll_languages_list( array( 'fields' => 'slug' ) );
			$pairs = array();
			foreach ( (array) $request['translations'] as $lang => $id ) {
				$lang = sanitize_key( $lang );
				$id   = (int) $id;
				if ( ! in_array( $lang, $langs, true ) || ! get_term( $id ) ) {
					return new WP_Error( 'ondo_bad_pair', '연결할 수 없는 짝: ' . $lang . '=' . $id, array( 'status' => 400 ) );
				}
				if ( pll_get_term_language( $id, 'slug' ) !== $lang ) { pll_set_term_language( $id, $lang ); }
				$pairs[ $lang ] = $id;
			}
			if ( count( $pairs ) < 2 ) { return new WP_Error( 'ondo_need_two', '두 언어 이상이 필요합니다.', array( 'status' => 400 ) ); }
			pll_save_term_translations( $pairs );
			$out = array(); $ok = true;
			foreach ( $pairs as $lang => $id ) {
				$st = ondo_term_state( $id ); $out[] = $st;
				foreach ( $pairs as $l2 => $i2 ) { $t = (array) $st['translations']; if ( ! isset( $t[ $l2 ] ) || (int) $t[ $l2 ] !== $i2 ) { $ok = false; } }
			}
			return array( 'linked' => $ok, 'terms' => $out );
		},
	) );
} );

// 1.4.3 (2026-11-25): 글 공유 미리보기 그림(og:image)을 '계산노트' 카드로 - 사용자 확정. Rank Math의 글별 공유 그림 칸에 넣음
// (블로그 화면의 대표 이미지·본문은 그대로). POST /ondo/v1/og-image {post, media} / GET /ondo/v1/og-image/<post>
add_action( 'rest_api_init', function () {
	register_rest_route( 'ondo/v1', '/og-image', array(
		'methods'             => 'POST',
		'permission_callback' => function () { return current_user_can( 'edit_posts' ); },
		'args'                => array( 'post' => array( 'required' => true ), 'media' => array( 'required' => true ) ),
		'callback'            => function ( $request ) {
			$post  = (int) $request['post'];
			$media = (int) $request['media'];
			if ( ! get_post( $post ) || ! current_user_can( 'edit_post', $post ) ) {
				return new WP_Error( 'ondo_bad_post', '글 없음: ' . $post, array( 'status' => 400 ) );
			}
			$url = wp_get_attachment_url( $media );
			if ( ! $url ) {
				return new WP_Error( 'ondo_bad_media', '그림 없음: ' . $media, array( 'status' => 400 ) );
			}
			update_post_meta( $post, 'rank_math_facebook_image', $url );
			update_post_meta( $post, 'rank_math_facebook_image_id', $media );
			update_post_meta( $post, 'rank_math_twitter_use_facebook', 'on' );
			return array( 'post' => $post, 'url' => $url );
		},
	) );
	register_rest_route( 'ondo/v1', '/og-image/(?P<post>\d+)', array(
		'methods'             => 'GET',
		'permission_callback' => function () { return current_user_can( 'edit_posts' ); },
		'callback'            => function ( $request ) {
			$post = (int) $request['post'];
			return array( 'post' => $post, 'url' => get_post_meta( $post, 'rank_math_facebook_image', true ),
				'twitter_use_facebook' => get_post_meta( $post, 'rank_math_twitter_use_facebook', true ) );
		},
	) );
} );

// 1.4.2 (2026-11-25): 네이버 서치어드바이저 소유 확인 태그(공개 값 - 사용자가 받아 줌). 첫 화면에만 있으면 되지만 모든 화면에 넣어도 무해.
add_action( 'wp_head', function () {
	echo '<meta name="naver-site-verification" content="7ce78d43ca429e49f89378e47702adfeb975b83e" />' . "\n";
}, 1 );

// 머리글 국기 버튼용: 지금 보는 화면의 각 언어판 주소(번역이 없으면 그 언어 첫 화면)
add_action( 'wp_head', function () {
	if ( ! function_exists( 'pll_the_languages' ) ) { return; }
	$list = pll_the_languages( array( 'raw' => 1, 'hide_if_empty' => 0, 'hide_if_no_translation' => 0 ) );
	$out  = array();
	foreach ( (array) $list as $l ) {
		$out[] = array( 'slug' => $l['slug'], 'url' => $l['url'], 'current' => ! empty( $l['current_lang'] ), 'missing' => ! empty( $l['no_translation'] ) );
	}
	echo '<script>window.ondoLang=' . wp_json_encode( $out ) . ';</script>' . "\n";
}, 1 );

/*
 * 1.2.0 (2026-11-20): Rank Math 사이트맵 진단·캐시 비우기.
 * 왜: 글 사이트맵이 7월 상태(비공개로 내린 옛 글 2개)로 멈추고 11-19 공개 글 4편이 빠짐. 응답은 매번 새로 만들어지는데(화면 캐시 아님)
 * 글 목록만 옛것 → Rank Math 내부 캐시로 보임. REST의 toolsAction·updateSettings는 실패(Something went wrong / 500).
 * GET  /ondo/v1/sitemap  - 사이트맵 설정(rank-math-options-sitemap 중 글·페이지·분류 관련 키만), 공개 글 수, 캐시 관련 옵션 이름
 * POST /ondo/v1/sitemap  - Rank Math 자체 함수로 사이트맵 캐시 비우기(+ 'rank_math_sitemap' 이름의 임시값 삭제). 설정은 바꾸지 않음.
 */
add_action( 'rest_api_init', function () {
	register_rest_route( 'ondo/v1', '/sitemap', array(
		array(
			'methods'             => 'GET',
			'permission_callback' => function () { return current_user_can( 'manage_options' ); },
			'callback'            => function () {
				global $wpdb;
				$opt  = get_option( 'rank-math-options-sitemap', array() );
				$keep = array();
				foreach ( (array) $opt as $k => $v ) {
					if ( preg_match( '/^(pt_|tax_|items_per_page|exclude|include_|authors_|ping|html_)/', $k ) ) {
						$keep[ $k ] = is_scalar( $v ) ? $v : wp_json_encode( $v );
					}
				}
				$names = $wpdb->get_col( "SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE '%rank_math%sitemap%' OR option_name LIKE '%rank-math%sitemap%' LIMIT 40" );
				$counts = wp_count_posts( 'post' );
				$modules = get_option( 'rank_math_modules', array() );
				return array(
					'settings'        => $keep,
					'sitemap_module'  => in_array( 'sitemap', (array) $modules, true ),
					'publish_posts'   => isset( $counts->publish ) ? (int) $counts->publish : null,
					'private_posts'   => isset( $counts->private ) ? (int) $counts->private : null,
					'cache_options'   => $names,
					'cache_class'     => class_exists( '\RankMath\Sitemap\Cache' ),
					'object_cache'    => wp_using_ext_object_cache(),
				);
			},
		),
		array(
			'methods'             => 'POST',
			'permission_callback' => function () { return current_user_can( 'manage_options' ); },
			'callback'            => function () {
				global $wpdb;
				$done = array();
				if ( class_exists( '\RankMath\Sitemap\Cache' ) ) {
					if ( method_exists( '\RankMath\Sitemap\Cache', 'invalidate_storage' ) ) { \RankMath\Sitemap\Cache::invalidate_storage(); $done[] = 'invalidate_storage'; }
					if ( method_exists( '\RankMath\Sitemap\Cache', 'clear' ) ) { \RankMath\Sitemap\Cache::clear(); $done[] = 'clear'; }
				}
				$rows = $wpdb->get_col( "SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE '\_transient\_%rank_math%sitemap%' OR option_name LIKE '\_transient\_timeout\_%rank_math%sitemap%'" );
				foreach ( $rows as $name ) {
					$key = preg_replace( '/^_transient_(timeout_)?/', '', $name );
					delete_transient( $key );
				}
				$done[] = 'transients:' . count( $rows );
				if ( function_exists( 'wp_cache_flush_group' ) ) { wp_cache_flush_group( 'rank_math' ); $done[] = 'cache_group'; }
				do_action( 'rank_math/sitemap/invalidate' );
				return array( 'done' => $done );
			},
		),
	) );
} );

/*
 * 1.3.0 (2026-11-22): 검색 결과에 보이는 첫 화면 제목·설명과 구조화 데이터 바로잡기(Rank Math 설정은 건드리지 않고 화면 출력만 바꿈).
 * 왜(lab/THINKING.txt 11-22 100바퀴): 첫 화면 설명이 옛 문구('리서치·정리해 … 인사이트를 제공하는 콘텐츠 채널'),
 *   영어 첫 화면(/en/)의 제목·설명이 한국어, 정책·지도 '페이지'가 BlogPosting(글)로 표시, 저자 sameAs가 옛 주소(ondo99.wordpress.com).
 * 되돌리기: 이 블록을 지우고 플러그인을 다시 올리면 원래대로.
 */
function ondo_seo_lang() {
	return function_exists( 'pll_current_language' ) ? pll_current_language( 'slug' ) : 'ko';
}
function ondo_seo_is_home() {
	return is_front_page() || is_home();
}
add_filter( 'rank_math/frontend/title', function ( $title ) {
	if ( ! ondo_seo_is_home() ) { return $title; }
	return 'en' === ondo_seo_lang()
		? 'ondo99 - ETF, dividend and currency numbers on the same basis'
		: 'ondo99 - ETF·배당·환율 숫자를 같은 기준으로 계산하는 블로그';
}, 20 );
add_filter( 'rank_math/frontend/description', function ( $desc ) {
	if ( ! ondo_seo_is_home() ) { return $desc; }
	return 'en' === ondo_seo_lang()
		? 'What does a 0.1% ETF fee gap cost after 10 years? ETF returns, dividends and currency effects, calculated over the same period on the same basis. Information only, not investment advice.'
		: 'ETF 보수 0.1% 차이는 10년 뒤 얼마일까? ETF·배당·환율을 같은 기간, 같은 기준으로 계산해 숫자로 보여 줍니다. 투자 권유가 아닌 정보 제공용입니다.';
}, 20 );
add_filter( 'rank_math/json_ld', function ( $data, $jsonld = null ) {
	if ( ! is_array( $data ) ) { return $data; }
	foreach ( $data as $key => $node ) {
		if ( ! is_array( $node ) ) { continue; }
		// 페이지(소개·정책·지도)는 글(BlogPosting)이 아님 - WebPage 노드만 남김
		if ( is_page() && isset( $node['@type'] ) && in_array( $node['@type'], array( 'BlogPosting', 'Article', 'NewsArticle' ), true ) ) {
			unset( $data[ $key ] );
			continue;
		}
		// 저자·사이트 대표의 옛 주소(ondo99.wordpress.com) 지우기
		if ( isset( $node['sameAs'] ) ) {
			$same = array_values( array_filter( (array) $node['sameAs'], function ( $u ) { return false === strpos( (string) $u, 'wordpress.com' ); } ) );
			if ( $same ) { $data[ $key ]['sameAs'] = $same; } else { unset( $data[ $key ]['sameAs'] ); }
		}
	}
	return $data;
}, 99, 2 );

// 1.4.0 (11-22): IndexNow 키 파일 - https://ondo99.com/<키>.txt 가 키 글자만 돌려줌(같은 호스트여야 함, ondo/indexnow.py와 같은 값)
define( 'ONDO_INDEXNOW_KEY', '6816a36f143a41b8a683b233a22b322f' );
add_action( 'init', function () {
	$path = parse_url( isset( $_SERVER['REQUEST_URI'] ) ? $_SERVER['REQUEST_URI'] : '', PHP_URL_PATH );
	if ( $path === '/' . ONDO_INDEXNOW_KEY . '.txt' ) {
		header( 'Content-Type: text/plain; charset=utf-8' );
		echo ONDO_INDEXNOW_KEY;
		exit;
	}
}, 0 );
